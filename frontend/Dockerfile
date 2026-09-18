# Optional: build and serve the report viewer as a static site with nginx.
#
# This toolkit is a CLI, not a live service, so there is no docker-compose
# stack here -- this Dockerfile just packages the already-static Vite build
# output behind a tiny web server, for the case where a customer or team
# wants to view a report from a browser without running `npm` themselves.
#
# Build:  docker build -t camtoolkit-report-viewer ./frontend
# Run:    docker run --rm -p 8080:80 camtoolkit-report-viewer
# Then open http://localhost:8080
#
# To view a real survey's report instead of the bundled sample data, drop
# your own report.json in before building (or bind-mount it at runtime):
#   docker run --rm -p 8080:80 \
#     -v "$(pwd)/report.json:/usr/share/nginx/html/sample-report.json:ro" \
#     camtoolkit-report-viewer

FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
