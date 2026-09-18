# Report Viewer

A React + TypeScript app that renders a `camtoolkit survey` report
(`report.json`) as a presentable camera inventory / RTSP health / network
readiness page. See the "Report Viewer" section in the repo root
[`README.md`](../README.md) for what it shows and how to point it at a
real survey's output.

```bash
npm install
npm run dev        # dev server with the bundled sample report
npm run build       # production build -> dist/
npx tsc -b --noEmit  # type-check only
```
