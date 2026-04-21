# Protocol Dashboard

Interactive HTML visualization of the UMBUS protocol. Shows frame types, timing diagrams, field layouts, and live decode examples.

## Viewing

Open `index.html` in any modern browser. No server required — it's a self-contained single-page app.

## Regenerating

The dashboard is generated from capture data by `tools/build-dashboard.py`:

```bash
su 0 python3 tools/build-dashboard.py
```

This reads parsed frame data from `captures/` and produces `dashboard/index.html`.
