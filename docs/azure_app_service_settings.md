# Azure App Service settings JSON

## Generate the private file

The generator reads production values from the Git-ignored root `.env` and
writes `scripts/deploy/azure_app_settings.json` with mode `0600`. It is an
Azure-compatible array of `{name, value, slotSetting}` objects and is ignored
by Git. It intentionally excludes the existing ACR registry settings.

From the repository root, set the HTTPS frontend URL that is active at
deployment time:

```bash
conda run -n agenda python scripts/deploy/generate_azure_app_settings.py \
  --frontend-url https://your-app.azurewebsites.net
```

After the custom domain and managed certificate are active, regenerate the
file with that HTTPS domain and import the replacement settings. Do not commit,
share, or paste the generated JSON into source control.
