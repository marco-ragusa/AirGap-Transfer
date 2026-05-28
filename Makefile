.PHONY: install test build clean

install:
	pip install -r requirements.txt

test:
	python -m pytest tests/ -v

build:
	cd reader && pyinstaller QRReader.spec

clean:
	rm -rf reader/dist reader/build
