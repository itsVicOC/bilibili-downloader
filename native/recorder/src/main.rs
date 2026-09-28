mod relay;

use flv_fix::{FlvPipeline, FlvPipelineConfig, FlvWriter, FlvWriterConfig};
use futures::{Stream, StreamExt};
use hls_fix::{HlsPipeline, HlsPipelineConfig, HlsWriter, HlsWriterConfig};
use mesio_engine::{
    DownloadRequest, DownloaderConfig, FlvProtocolBuilder, HlsProtocolBuilder, MesioConfig,
    MesioDownloader,
};
use pipeline_common::{
    CancellationToken, ChannelSpec, PipelineError, PipelineProvider, ProtocolWriter,
    StreamerContext, WriterProgress, WriterStats, config::PipelineConfig, settle_run,
    spawn_pipeline,
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    io::{BufRead, Read, Write},
    path::PathBuf,
    pin::Pin,
    sync::{Arc, Mutex, mpsc},
    time::Duration,
};

const PROTOCOL: u32 = 1;
const ENGINE_REVISION: &str = "1897d736a4560f267700d7c4c1cf02dffc3c4c56";

fn validate_flv(item: flv::FlvData) -> Result<flv::FlvData, PipelineError> {
    if let flv::FlvData::Tag(tag) = &item {
        let codec = tag.classification().codec;
        if tag.is_filtered()
            || (tag.is_video_tag() && codec != Some(flv::CodecKind::Avc))
            || (tag.is_audio_tag() && codec != Some(flv::CodecKind::Aac))
        {
            return Err(PipelineError::Strategy(Box::new(std::io::Error::other(
                "encrypted_or_unsupported_flv",
            ))));
        }
    }
    Ok(item)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Start {
    v: u32,
    command: String,
    url: String,
    output_dir: PathBuf,
    format: String,
    segment_seconds: u32,
}

#[derive(Clone)]
struct Events {
    // Lifecycle events are lossless; progress uses a single coalescing slot.
    tx: mpsc::Sender<Value>,
    progress: Arc<Mutex<Option<Value>>>,
    pending_segment: Arc<Mutex<Option<Value>>>,
}

impl Events {
    fn send(&self, value: Value) {
        let _ = self.tx.send(value);
    }
    fn flush_segment(&self) {
        if let Some(value) = self.pending_segment.lock().unwrap().take() {
            // HLS may open an empty file after the final split marker. It is
            // not a recording segment. The handle is closed at this point.
            if value["bytes"] == 0 {
                if let Some(path) = value["path"].as_str()
                    && std::fs::metadata(path).is_ok_and(|m| m.len() == 0)
                {
                    let _ = std::fs::remove_file(path);
                }
                return;
            }
            self.send(value);
        }
    }
    fn metrics(&self, value: WriterProgress) {
        *self.progress.lock().unwrap() =
            Some(json!({"event":"metrics", "bytes":value.bytes_written_total,
            "duration":value.media_duration_secs_total, "speed":value.speed_bytes_per_sec}));
    }
}

fn output_thread(token: CancellationToken) -> (Events, std::thread::JoinHandle<()>) {
    let (tx, rx) = mpsc::channel::<Value>();
    let progress = Arc::new(Mutex::new(None));
    let copy = progress.clone();
    let output = std::thread::spawn(move || {
        let mut stdout = std::io::stdout().lock();
        loop {
            let value = match rx.recv_timeout(Duration::from_millis(200)) {
                Ok(value) => Some(value),
                Err(mpsc::RecvTimeoutError::Timeout) => copy.lock().unwrap().take(),
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            };
            if let Some(mut value) = value {
                value["v"] = json!(PROTOCOL);
                let terminal = value["event"] == "stopped";
                if serde_json::to_writer(&mut stdout, &value).is_err()
                    || writeln!(stdout).is_err()
                    || stdout.flush().is_err()
                {
                    token.cancel();
                    break;
                }
                if terminal {
                    break;
                }
            }
        }
    });
    (
        Events {
            tx,
            progress,
            pending_segment: Arc::new(Mutex::new(None)),
        },
        output,
    )
}

async fn process<P, W>(
    mut stream: Pin<Box<dyn Stream<Item = Result<P::Item, PipelineError>> + Send>>,
    common: &PipelineConfig,
    config: P::Config,
    channel: ChannelSpec<P::Item>,
    mut writer: W,
) -> Result<WriterStats, String>
where
    P: PipelineProvider,
    P::Config: Send + 'static,
    P::Item: Send + 'static,
    W: ProtocolWriter<Item = P::Item>,
{
    // Cancelling the downloader closes input. Keep the processing context alive
    // so already received media is drained and writers can flush their tails.
    let context = Arc::new(StreamerContext::new(CancellationToken::new()));
    let pipeline = P::with_config(context, common, config).build_pipeline();
    let spawned = spawn_pipeline(pipeline, channel);
    let writer_task = tokio::task::spawn_blocking(move || writer.run(spawned.output_rx));
    while let Some(item) = stream.next().await {
        if spawned.input_tx.send(item).await.is_err() {
            break;
        }
    }
    drop(spawned.input_tx);
    let result = writer_task.await.map_err(|_| "writer_failed")?;
    settle_run(result, spawned.tasks)
        .await
        .map_err(|_| "media_processing_failed".into())
}

macro_rules! callbacks {
    ($writer:ident, $events:ident) => {
        let events = $events.clone();
        $writer.set_on_segment_start_callback(move |_, _| { events.flush_segment(); });
        let events = $events.clone();
        $writer.set_on_segment_complete_callback(move |path, sequence, duration, bytes, _| {
            // Upstream invokes this after flush but before dropping the file.
            // Publish only on the NEXT open or after writer.run has returned.
            *events.pending_segment.lock().unwrap() = Some(json!({"event":"segment_finalized",
                "path":path, "sequence":sequence, "duration":duration, "bytes":bytes}));
        });
        let events = $events.clone();
        $writer.set_progress_callback(move |progress| events.metrics(progress));
    };
}

async fn record(
    start: Start,
    token: CancellationToken,
    events: Events,
) -> Result<WriterStats, String> {
    if start.v != PROTOCOL
        || start.command != "start"
        || !(1..=86400).contains(&start.segment_seconds)
        || !["flv", "ts", "fmp4"].contains(&start.format.as_str())
        || !start.output_dir.is_absolute()
    {
        return Err("invalid_start".into());
    }
    relay::validate_url(&start.url)?;
    std::fs::create_dir_all(&start.output_dir).map_err(|_| "output_directory_failed")?;
    if std::fs::read_dir(&start.output_dir)
        .map_err(|_| "output_directory_failed")?
        .next()
        .is_some()
    {
        return Err("output_directory_not_empty".into());
    }
    let (url, relay_task) = relay::start(&start.url, events.clone(), token.clone()).await?;
    let base = DownloaderConfig::builder()
        .with_system_proxy(false)
        .with_follow_redirects(false)
        .with_connect_timeout(Duration::from_secs(10))
        .with_read_timeout(Duration::from_secs(35))
        .with_caching_enabled(false)
        .build();
    let flv = FlvProtocolBuilder::new()
        .with_config(|c| c.base = base.clone())
        .get_config();
    let hls = HlsProtocolBuilder::new()
        .with_base_config(base)
        .download_concurrency(2)
        .get_config();
    let downloader = MesioDownloader::new(MesioConfig {
        flv,
        hls,
        token: token.clone(),
    });
    let common = PipelineConfig::builder()
        .max_duration_s(start.segment_seconds as f64)
        .channel_size(16)
        .build();
    let request = DownloadRequest::from_url(&url)
        .map_err(|_| "invalid_media_url")?
        .with_cancel(token.clone());
    events.send(json!({"event":"started"}));
    let result = async {
        if start.format == "flv" {
            let session = downloader
                .start_flv(request)
                .await
                .map_err(|_| "media_open_failed")?;
            let mut writer = FlvWriter::new(FlvWriterConfig {
                output_dir: start.output_dir,
                base_name: "part_%i".into(),
            });
            callbacks!(writer, events);
            let stream = session.items.map(|r| {
                r.map_err(|e| PipelineError::Strategy(Box::new(e)))
                    .and_then(validate_flv)
            });
            process::<FlvPipeline, _>(
                Box::pin(stream),
                &common,
                FlvPipelineConfig::default(),
                ChannelSpec::items(16),
                writer,
            )
            .await
        } else {
            let session = downloader
                .start_hls(request)
                .await
                .map_err(|_| "media_open_failed")?;
            #[cfg(feature = "test-fixtures")]
            tokio::spawn(async move {
                let mut diagnostics = session.events;
                while let Some(event) = diagnostics.next().await {
                    use mesio_engine::session::DownloadEvent;
                    match event {
                        DownloadEvent::ResourceStarted { content_length, .. } => {
                            eprintln!("fixture resource started: {content_length:?} bytes")
                        }
                        DownloadEvent::ResourceFinished { bytes, .. } => {
                            eprintln!("fixture resource finished: {bytes} bytes")
                        }
                        DownloadEvent::GapSkipped {
                            from_sequence,
                            to_sequence,
                            reason,
                        } => eprintln!("fixture gap: {from_sequence}-{to_sequence} {reason:?}"),
                        DownloadEvent::RetryScheduled { attempt, delay, .. } => {
                            eprintln!("fixture retry: {attempt} after {delay:?}")
                        }
                        _ => (),
                    }
                }
            });
            let mut writer = HlsWriter::new(HlsWriterConfig {
                output_dir: start.output_dir,
                base_name: "part_%i".into(),
                extension: if start.format == "ts" { "ts" } else { "m4s" }.into(),
                max_file_size: None,
            });
            callbacks!(writer, events);
            let stream = session
                .items
                .map(|r| r.map_err(|e| PipelineError::Strategy(Box::new(e))));
            process::<HlsPipeline, _>(
                Box::pin(stream),
                &common,
                HlsPipelineConfig::default(),
                HlsPipeline::channel_spec(16),
                writer,
            )
            .await
        }
    }
    .await;
    events.flush_segment();
    relay_task.abort();
    result
}

fn ready() -> Value {
    json!({"event":"ready", "name":"biliflow-recorder", "version":env!("CARGO_PKG_VERSION"),
    "engine_revision":ENGINE_REVISION, "formats":["flv","ts","fmp4"], "test_fixtures":cfg!(feature="test-fixtures")})
}

#[tokio::main]
async fn main() {
    if std::env::args().any(|arg| arg == "--check") {
        let mut value = ready();
        value["v"] = json!(PROTOCOL);
        println!("{value}");
        return;
    }
    let token = CancellationToken::new();
    let (events, output) = output_thread(token.clone());
    events.send(ready());
    // The parent may already be gone, so the adapter needs its own bound too.
    // Unfinished files stay on disk; no finalized event is invented on timeout.
    let watchdog_token = token.clone();
    let watchdog_events = events.clone();
    let watchdog = tokio::spawn(async move {
        watchdog_token.cancelled().await;
        tokio::time::sleep(Duration::from_secs(8)).await;
        watchdog_events.send(json!({"event":"error", "code":"shutdown_timeout"}));
        watchdog_events.send(json!({"event":"stopped", "reason":"interrupted"}));
        tokio::time::sleep(Duration::from_millis(100)).await;
        std::process::exit(3);
    });
    let (start_tx, start_rx) = tokio::sync::oneshot::channel();
    let reader_token = token.clone();
    std::thread::spawn(move || {
        let mut reader = std::io::stdin().lock();
        let mut line = String::new();
        // Limit every command; URLs never become logs or process arguments.
        let read = (&mut reader).take(65537).read_line(&mut line);
        if read.is_err() || line.len() > 65536 {
            reader_token.cancel();
            return;
        }
        if start_tx.send(serde_json::from_str::<Start>(&line)).is_err() {
            return;
        }
        // This process handles one recording. Its only subsequent command is
        // stop; EOF, malformed/oversized commands and I/O errors also fail closed.
        line.clear();
        let _ = (&mut reader).take(65537).read_line(&mut line);
        reader_token.cancel();
    });
    let result = match start_rx.await {
        Ok(Ok(start)) => record(start, token.clone(), events.clone()).await,
        _ => Err("invalid_start".into()),
    };
    match result {
        Ok(stats) => events.send(
            json!({"event":"stopped", "reason":if token.is_cancelled() {"requested"} else {"eof"},
            "bytes":stats.bytes_written, "duration":stats.duration_secs}),
        ),
        Err(code) => {
            events.send(json!({"event":"error", "code":code}));
            events.send(json!({"event":"stopped", "reason":"error"}));
        }
    }
    drop(events);
    let _ = tokio::task::spawn_blocking(move || output.join()).await;
    watchdog.abort();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_filtered_and_non_avc_flv_tags() {
        let tag = flv::FlvTag::new(0, 0, flv::FlvTagType::Video, true, vec![0x17, 0].into());
        assert!(validate_flv(flv::FlvData::Tag(tag)).is_err());
        let tag = flv::FlvTag::new(0, 0, flv::FlvTagType::Video, false, vec![0x1c, 0].into());
        assert!(validate_flv(flv::FlvData::Tag(tag)).is_err());
    }
}
