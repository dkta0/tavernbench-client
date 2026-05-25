.PHONY: build test e2e clean

build:
	cd tui && go build -o tavernbench-tui .
	cd cli && go build -o tavernbench ./cmd/tavernbench

test:
	cd tui && go test ./...
	cd cli && go test ./...

e2e: build
	chmod +x e2e/smoke.sh
	./e2e/smoke.sh

clean:
	rm -f tui/tavernbench-tui cli/tavernbench
