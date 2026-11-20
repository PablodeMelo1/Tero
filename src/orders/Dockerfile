FROM golang:1.27-bookworm@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea AS build
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -mod=readonly -trimpath -ldflags="-s -w" -o /out/orders .

FROM debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3
WORKDIR /app
COPY --from=build /out/orders /app/orders
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=12 CMD ["/app/orders", "--healthcheck"]
CMD ["/app/orders"]
