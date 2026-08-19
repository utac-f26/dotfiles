# Secrets

This directory is for SOPS-encrypted dotenv files. Plaintext `.env` files should
not be committed.

`./setup` creates an age key at:

```text
~/.config/sops/age/keys.txt
```

It then writes `.sops.yaml` in the repo with your public age recipient. Do not
overwrite an existing age key; if you lose it, files encrypted to that key cannot
be decrypted.

Dummy round-trip:

```bash
printf 'EXAMPLE_SECRET=hello\n' > /tmp/example.env
sops -e --filename-override secrets/example.env \
    --input-type dotenv --output-type dotenv /tmp/example.env > secrets/example.env
with-secrets secrets/example.env -- sh -c 'test "$EXAMPLE_SECRET" = hello'
```

`--filename-override` is required: sops matches `.sops.yaml` creation rules
against the input path, and `/tmp/example.env` matches no rule. The override
applies the `secrets/*.env` rule without ever writing plaintext inside the repo.

`with-secrets` delegates environment injection to `sops exec-env`. Decrypted
values exist only in process memory; the wrapper does not create a plaintext
temporary file. When several encrypted files are supplied, later files override
earlier files.

`utmail.env.example` is a placeholder for a future email component. It is not an
operational credential file.
