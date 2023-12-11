# See: https://clarkgrubb.com/makefile-style-guide
MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := all
.DELETE_ON_ERROR:
.SUFFIXES:

# version of loader
DATE:=$(shell date '+%Y%m%d-%H%M%S')

# This will output the help for each task
# See: https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
.PHONY: help
help: ## Print usage help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
.DEFAULT_GOAL := help


.PHONY: codegen
codegen: ## Run the codegen using bun inside docker
	DOCKER_BUILDKIT=1 \
	docker build \
		--target output \
		--progress=plain \
		--output build \
		. && \
	ln -s `pwd`/codegen build/codegen

.PHONY: fetch
fetch:  ## Fetch wgpu_native from github release
	python docker/fetch-native.py --install wgpu_native

.PHONY: build
build: clean codegen fetch ## Run all steps of the build process.
	cd build && \
	python wgpu_native_build.py && \
	cd .. && mkdir webgoo && \
	cp build/webgoo.py webgoo/__init__.py && \
	cp build/*.so webgoo/ && \
	patchelf --set-rpath '$$ORIGIN'/ webgoo/_wgpu_native_cffi.*

.PHONY: clean
clean: ## Remove built files.
	rm -rf build webgoo
