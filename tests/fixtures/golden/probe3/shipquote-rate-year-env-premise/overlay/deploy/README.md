# Deploy environments

The checkout service runs shipquote in-process. Each file here is the environment of one
deployment of the checkout's quoting worker: `KEY=value` lines, read at start-up, no quoting
and no expansion. Changes go live on the next deploy of that environment.

- `staging.env`: staging (checkout.staging.example)
- `production.env`: production
