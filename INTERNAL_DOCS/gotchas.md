# Gotchas

Common pitfalls and non-obvious behaviors encountered during development.

1. **Anaconda.org doesn't provide digests** - Use `verify=False` when downloading
2. **Version specifiers with .dev releases** - Use `>=2.0.0.dev0` not `>=2.0.0a0` for dev releases
3. **pytest.skip() in fixtures** - Use assertions instead to avoid hiding failures
4. **pypi-simple is sync** - For async proxy, need to wrap or use httpx directly
5. **Wheel filenames must match internal metadata** - After renaming, filename, directory name, and METADATA Name must all match
