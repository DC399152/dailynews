# Tool security model

The model is treated as an untrusted caller. Tool arguments are validated with
Pydantic and expected policy failures are returned as structured observations. This
allows the model to select a safer alternative without exposing an unrestricted host
capability.

## Filesystem boundary

`list_dir`, `read_file`, `search_content`, and `write_file` operate under one resolved
workspace root.

Controls:

- reject absolute paths, null bytes, `..` escape, and symlinks resolving outside root;
- cap read and write byte counts;
- accept UTF-8 text only;
- do not follow symlinked directories during recursive search;
- cap search results and individual result previews;
- use a temporary file plus `os.replace` for atomic writes.

There remains a narrow time-of-check/time-of-use race if another trusted host process
mutates workspace symlinks concurrently. A production hostile-tenant deployment would
add an OS or container sandbox rather than relying on path checks alone.

## Restricted `bash`

The assignment calls the tool `bash`, but it deliberately does not launch a shell.
It parses one command with `shlex` and invokes it through
`asyncio.create_subprocess_exec`.

Controls:

- allow only `date`, `head`, `ls`, `pwd`, `sort`, `tail`, `uniq`, and `wc`;
- reject shell operators, redirects, substitutions, absolute executables, and unsafe
  options;
- validate file arguments against the same workspace policy;
- run with a fixed working directory and a minimal `PATH`/`LANG` environment;
- cap returned stdout/stderr;
- kill the child process when timeout cancellation occurs.

The Agent Loop's per-tool timeout supplies the outer execution deadline.

## News and article retrieval

`search_news` queries application-configured RSS endpoints. It applies freshness and
result limits, removes common tracking parameters, deduplicates normalized URLs, and
caps source responses.

`fetch_article` accepts model-controlled URLs, so it additionally:

- accepts HTTP/HTTPS and ports 80/443 only;
- rejects embedded URL credentials;
- resolves and rejects private, loopback, link-local, multicast, reserved, and
  otherwise non-global IP addresses;
- revalidates every redirect target;
- accepts text/plain and text/html only;
- streams responses under a byte limit and caps extracted article characters;
- removes scripts, styles, navigation, footers, SVG, and noscript elements.

DNS rebinding cannot be completely eliminated without connecting to the previously
validated IP address. Production deployment should enforce an egress proxy or network
policy in addition to application checks.

## Subscription and delivery

`get_subscription` exposes only the structured profile needed to personalize a run.
Its provider protocol will be backed by the Day 3 database repository.

`send_digest` resolves the recipient from that provider instead of accepting an
arbitrary email address from the model. It rejects header newlines. SMTP credentials
come only from environment configuration and are never placed in tool output. When
SMTP is disabled, the tool writes a JSON message into `workspace/outbox/` for local
and CI verification.
