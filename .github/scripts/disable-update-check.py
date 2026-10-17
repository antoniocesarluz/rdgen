#!/usr/bin/env python3
r"""Disable the software-update check in RustDesk's src/common.rs.

Why this exists
---------------
Upstream rdgen patched the update check with:

    sed -i '/let (request, url) =/,/Ok(())/{/Ok(())/!d}' ./src/common.rs

That range starts at the first `let (request, url) =` (line 1133, inside
do_check_software_update) but only *ends* at the next line containing `Ok(())`
-- which is ~1100 lines later, in an unrelated function. It therefore deleted
1100+ lines and left an orphaned `}`:

    error: unexpected closing delimiter: `}`
       --> src\common.rs:1136:1

The step carries `continue-on-error: true`, so the workflow kept going with an
already-broken file and only died later in `cargo build`.

This replaces the whole function by brace depth with a stub that returns
Ok(()), which is what the caller expects:

    std::thread::spawn(move || allow_err!(do_check_software_update()));

Idempotent: if the function is already a stub, it does nothing.
"""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "src/common.rs"
SIG = "pub async fn do_check_software_update"

STUB = [
    "    // rdgen: software update check disabled (removeNewVersionNotif)",
    "    let _ = ();",
    "    Ok(())",
    "}",
]

lines = open(PATH, encoding="utf-8").read().split("\n")

if any(SIG in l for l in lines) is False:
    # function may already be stubbed; verify we can find its closing brace
    pass

try:
    fn = next(i for i, l in enumerate(lines) if SIG in l)
except StopIteration:
    print(f"rdgen-patch: {SIG} not found in {PATH}; nothing to do")
    sys.exit(0)

# Preserve any attribute lines immediately above the signature (e.g. #[tokio::main]).
attr = fn
while attr > 0 and lines[attr - 1].lstrip().startswith("#["):
    attr -= 1

depth = 0
started = False
end = None
for i in range(fn, len(lines)):
    depth += lines[i].count("{") - lines[i].count("}")
    if "{" in lines[i]:
        started = True
    if started and depth == 0:
        end = i
        break

if end is None:
    print("rdgen-patch: could not find closing brace; leaving file untouched")
    sys.exit(1)

body = "\n".join(lines[fn:end + 1])
if "let _ = ();" in body:
    print("rdgen-patch: already stubbed; no change")
    sys.exit(0)

out = lines[:attr] + lines[attr:fn] + [lines[fn]] + STUB + lines[end + 1:]
text = "\n".join(out)

delta = text.count("{") - text.count("}")
if delta != 0:
    print(f"rdgen-patch: refusing to write, braces unbalanced (delta={delta})")
    sys.exit(1)

open(PATH, "w", encoding="utf-8").write(text)
print(f"rdgen-patch: disabled update check in {PATH} "
      f"(lines {attr + 1}-{end + 1}, {end + 1 - attr - 3} removed)")