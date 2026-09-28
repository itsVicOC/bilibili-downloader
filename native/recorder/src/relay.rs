//! A per-recording loopback relay. Every upstream request (including HLS child
//! resources and redirects) passes the same HTTPS/domain and encryption policy.
use axum::{
    Router,
    body::Body,
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    response::Response,
    routing::get,
};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use futures::StreamExt;
use regex::Regex;
use std::{sync::Arc, time::Duration};
use url::Url;

#[derive(Clone)]
struct Relay {
    client: reqwest::Client,
    prefix: String,
    events: crate::Events,
    token: pipeline_common::CancellationToken,
}

impl Relay {
    fn reject(&self, code: &str) -> StatusCode {
        self.events
            .send(serde_json::json!({"event":"error", "code":code}));
        self.token.cancel();
        StatusCode::FORBIDDEN
    }
}

pub fn validate_url(value: &str) -> Result<Url, String> {
    let url = Url::parse(value).map_err(|_| "invalid_url")?;
    #[cfg(feature = "test-fixtures")]
    if url.scheme() == "http" && url.host_str() == Some("127.0.0.1") {
        return Ok(url);
    }
    let host = url.host_str().unwrap_or("");
    let trusted = [
        "bilivideo.com",
        "bilivideo.cn",
        "bilibili.com",
        "hdslb.com",
        "edge.mountaintoys.cn",
    ]
    .iter()
    .any(|d| host == *d || host.ends_with(&format!(".{d}")));
    if url.scheme() != "https"
        || !trusted
        || url.port().is_some_and(|p| p != 443)
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err("untrusted_media_url".into());
    }
    Ok(url)
}

fn local_url(prefix: &str, url: &Url) -> String {
    let suffix = if url.path().ends_with(".m3u8") {
        "index.m3u8"
    } else {
        "media"
    };
    format!("{prefix}/{}/{suffix}", URL_SAFE_NO_PAD.encode(url.as_str()))
}

fn rewrite_playlist(text: &str, base: &Url, prefix: &str) -> Result<String, String> {
    if !text.trim_start().starts_with("#EXTM3U") {
        return Err("invalid_playlist".into());
    }
    let uri = Regex::new(r#"URI="([^"]*)""#).unwrap();
    let mut output = String::new();
    for line in text.lines() {
        let line = line.trim();
        if (line.starts_with("#EXT-X-KEY:") || line.starts_with("#EXT-X-SESSION-KEY:"))
            && line
                .split_once(':')
                .unwrap()
                .1
                .split(',')
                .filter(|s| s.starts_with("METHOD="))
                .collect::<Vec<_>>()
                != vec!["METHOD=NONE"]
        {
            return Err("encrypted_media_unsupported".into());
        }
        let rewrite = |value: &str| -> Result<String, String> {
            let target = base.join(value).map_err(|_| "invalid_playlist_url")?;
            validate_url(target.as_str())?;
            Ok(local_url(prefix, &target))
        };
        if line.starts_with('#') {
            if line.matches("URI=").count() != uri.captures_iter(line).count() {
                return Err("invalid_playlist_url".into());
            }
            let mut previous = 0;
            for captures in uri.captures_iter(line) {
                let matched = captures.get(1).unwrap();
                output.push_str(&line[previous..matched.start()]);
                output.push_str(&rewrite(matched.as_str())?);
                previous = matched.end();
            }
            output.push_str(&line[previous..]);
        } else if !line.is_empty() {
            output.push_str(&rewrite(line)?);
        }
        output.push('\n');
    }
    Ok(output)
}

async fn request(
    State(relay): State<Arc<Relay>>,
    Path((encoded, _suffix)): Path<(String, String)>,
    headers: HeaderMap,
) -> Result<Response, StatusCode> {
    let decoded = URL_SAFE_NO_PAD
        .decode(encoded)
        .map_err(|_| StatusCode::BAD_REQUEST)?;
    let mut url = validate_url(std::str::from_utf8(&decoded).map_err(|_| StatusCode::BAD_REQUEST)?)
        .map_err(|code| relay.reject(&code))?;
    for _ in 0..6 {
        let mut request = relay.client.get(url.clone());
        if let Some(range) = headers.get("range") {
            request = request.header("range", range);
        }
        let response = request.send().await.map_err(|_| StatusCode::BAD_GATEWAY)?;
        if response.status().is_redirection() {
            let target = response
                .headers()
                .get("location")
                .and_then(|v| v.to_str().ok())
                .ok_or(StatusCode::BAD_GATEWAY)?;
            url = validate_url(
                url.join(target)
                    .map_err(|_| StatusCode::BAD_GATEWAY)?
                    .as_str(),
            )
            .map_err(|code| relay.reject(&code))?;
            continue;
        }
        let status = response.status();
        if status.as_u16() == 412 || status.as_u16() == 429 {
            relay
                .events
                .send(serde_json::json!({"event":"error", "code":"rate_limited"}));
            relay.token.cancel();
            return Err(status);
        }
        if !status.is_success() {
            return Err(status);
        }
        let content_type = response
            .headers()
            .get("content-type")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("")
            .to_ascii_lowercase();
        let content_range = response.headers().get("content-range").cloned();
        let mut stream = response.bytes_stream();
        let mut bytes = Vec::new();
        while bytes.len() < 16 {
            match stream.next().await {
                Some(Ok(chunk)) => bytes.extend_from_slice(&chunk),
                Some(Err(_)) => return Err(StatusCode::BAD_GATEWAY),
                None => break,
            }
        }
        // Some CDNs omit a playlist extension or send the wrong content type.
        // Sniff too so such a playlist can never escape the relay unrewritten.
        let looks_like_playlist = bytes
            .first()
            .is_some_and(|b| *b == b'#' || b.is_ascii_whitespace())
            || bytes.starts_with(&[0xef, 0xbb, 0xbf]);
        if url.path().ends_with(".m3u8") || content_type.contains("mpegurl") || looks_like_playlist
        {
            if bytes.len() > 2 * 1024 * 1024 {
                return Err(StatusCode::PAYLOAD_TOO_LARGE);
            }
            while let Some(chunk) = stream.next().await {
                let chunk = chunk.map_err(|_| StatusCode::BAD_GATEWAY)?;
                if bytes.len() + chunk.len() > 2 * 1024 * 1024 {
                    return Err(StatusCode::PAYLOAD_TOO_LARGE);
                }
                bytes.extend_from_slice(&chunk);
            }
            let text = std::str::from_utf8(&bytes).map_err(|_| StatusCode::BAD_GATEWAY)?;
            let rewritten =
                rewrite_playlist(text, &url, &relay.prefix).map_err(|code| relay.reject(&code))?;
            return Ok(Response::builder()
                .header("content-type", "application/vnd.apple.mpegurl")
                .body(Body::from(rewritten))
                .unwrap());
        }
        let mut builder = Response::builder().status(status);
        if let Some(range) = content_range {
            builder = builder.header("content-range", range);
        }
        // Map reqwest errors to a fixed message; they can contain signed URLs.
        let prefix = futures::stream::once(async move { Ok::<_, reqwest::Error>(bytes.into()) });
        let body = prefix
            .chain(stream)
            .map(|r| r.map_err(|_| std::io::Error::other("media_read_failed")));
        return Ok(builder.body(Body::from_stream(body)).unwrap());
    }
    Err(StatusCode::BAD_GATEWAY)
}

pub async fn start(
    source: &str,
    events: crate::Events,
    token: pipeline_common::CancellationToken,
) -> Result<(String, tokio::task::JoinHandle<()>), String> {
    let _ = rustls::crypto::aws_lc_rs::default_provider().install_default();
    let source = validate_url(source)?;
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .map_err(|_| "relay_bind_failed")?;
    let prefix = format!(
        "http://{}/{}",
        listener.local_addr().map_err(|_| "relay_bind_failed")?,
        uuid::Uuid::new_v4()
    );
    let route = format!(
        "/{}/{{encoded}}/{{suffix}}",
        prefix.rsplit('/').next().unwrap()
    );
    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(10))
        .read_timeout(Duration::from_secs(30))
        .user_agent("Mozilla/5.0 BiliFlow/0.1")
        .default_headers(HeaderMap::from_iter([(
            "referer".parse().unwrap(),
            "https://live.bilibili.com/".parse().unwrap(),
        )]))
        .build()
        .map_err(|_| "http_client_failed")?;
    let url = local_url(&prefix, &source);
    let app = Router::new()
        .route(&route, get(request))
        .with_state(Arc::new(Relay {
            client,
            prefix,
            events,
            token,
        }));
    let handle = tokio::spawn(async move {
        let _ = axum::serve(listener, app).await;
    });
    Ok((url, handle))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_credentials_and_host_suffix_tricks() {
        for url in [
            "https://bilivideo.com.evil.test/a",
            "https://u:p@a.bilivideo.com/a",
            "https://a.bilivideo.com:8443/a",
            "file:///tmp/a",
        ] {
            assert!(validate_url(url).is_err());
        }
        assert!(validate_url("https://a.bilivideo.com/a?secret=x").is_ok());
    }
    #[test]
    fn rewrites_every_playlist_resource_and_rejects_encryption() {
        let base = Url::parse("https://a.bilivideo.com/live/index.m3u8").unwrap();
        let text = "#EXTM3U\n#EXT-X-MAP:URI=\"init.mp4\"\n#EXTINF:1,\nsegment.ts\n";
        let output = rewrite_playlist(text, &base, "http://127.0.0.1:1/token").unwrap();
        assert_eq!(output.matches("http://127.0.0.1:1/token/").count(), 2);
        assert!(
            rewrite_playlist("#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"key\"", &base, "p").is_err()
        );
        assert!(rewrite_playlist("#EXTM3U\nhttps://evil.test/seg.ts", &base, "p").is_err());
    }
}
