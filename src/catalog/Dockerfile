FROM golang:1.27
WORKDIR /app
COPY . .
RUN go mod download
RUN go build -o catalog .
EXPOSE 8080
CMD ["./catalog"]
