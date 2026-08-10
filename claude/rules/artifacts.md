# Artifacts

**Never publish an Artifact.** The Artifact tool uploads content to Anthropic's (claude.ai) servers, which leaks private machine contents off-machine — unacceptable even though artifacts are private-by-default.

- When asked for "an HTML", a report, or any visual output, write a **local HTML file** on disk with the Write tool and give the file path.
- Make it self-contained: inline all CSS/JS, no CDNs, works offline.
- Do not offer to publish or share.
