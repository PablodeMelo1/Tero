FROM golang:1.26-bookworm@sha256:23ce71337b726608afb1bc00986e630a05034a87a87ea1fc2cd1ae5cf33387eb AS build
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -mod=readonly -trimpath -ldflags="-s -w" -o /out/orders .

FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc
WORKDIR /app
COPY --from=build /out/orders /app/orders
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=12 CMD ["/app/orders", "--healthcheck"]
CMD ["/app/orders"]
