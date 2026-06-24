BASE_VERSION := 0.0.1
DEV_VERSION := $(BASE_VERSION)-dev
GIT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
ifeq ($(origin VERSION),undefined)
  ifeq ($(GIT_BRANCH),main)
    VERSION := $(BASE_VERSION)
  else
    VERSION := $(DEV_VERSION)
  endif
endif

CONTAINER_TOOL ?= podman
REGISTRY ?=
ARCH ?= linux/amd64
NAMESPACE ?=

# Pull policy: --policy=always for podman (pull newest); empty for docker (always pulls by default)
PULL_POLICY := $(if $(filter podman,$(CONTAINER_TOOL)),--policy=always,)

CODE_GEN_IMG ?= $(REGISTRY)/agent-mesh-for-sw-modernization-code-generation:$(VERSION)
DATA_GEN_IMG ?= $(REGISTRY)/agent-mesh-for-sw-modernization-data-generation:$(VERSION)
DATA_IDX_IMG ?= $(REGISTRY)/agent-mesh-for-sw-modernization-data-indexing:$(VERSION)

define build_image
	@echo "Building $(2)"
	$(CONTAINER_TOOL) build -t $(1) --platform=$(ARCH) -f $(3) $(4)
	@echo "Successfully built $(1)"
endef

define push_image
	@echo "Pushing $(2): $(1)"
	$(CONTAINER_TOOL) push $(1)
	@echo "Successfully pushed $(2)"
endef

##@ Image Build

build-all-images: build-code-gen-image build-data-gen-image build-data-idx-image

build-code-gen-image:
	$(call build_image,$(CODE_GEN_IMG),code-generation image,resources/code-generation/Containerfile,resources/code-generation)

build-data-gen-image:
	$(call build_image,$(DATA_GEN_IMG),data-generation image,resources/data-generation/Containerfile,resources/data-generation)

build-data-idx-image:
	$(call build_image,$(DATA_IDX_IMG),data-indexing image,resources/data-indexing/Containerfile,resources/data-indexing)

##@ Image Push

push-all-images: push-code-gen-image push-data-gen-image push-data-idx-image

push-code-gen-image:
	$(call push_image,$(CODE_GEN_IMG),code-generation image)

push-data-gen-image:
	$(call push_image,$(DATA_GEN_IMG),data-generation image)

push-data-idx-image:
	$(call push_image,$(DATA_IDX_IMG),data-indexing image)

##@ Notebooks

clean-notebooks:
	uv run --with nbstripout nbstripout workflows/code_understanding/*.ipynb
	uv run --with nbformat python -c "\
import nbformat, sys;\
[nbformat.write(nb := nbformat.read(p, as_version=4), p) for p in sys.argv[1:]]\
" workflows/code_understanding/*.ipynb

##@ Deployment

install:
	oc new-project $(NAMESPACE) 2>/dev/null || oc project $(NAMESPACE)
	oc label namespace $(NAMESPACE) opendatahub.io/dashboard=true --overwrite
	oc create secret generic code-understanding-env --from-env-file=.env -n $(NAMESPACE) 2>/dev/null || \
		oc create secret generic code-understanding-env --from-env-file=.env -n $(NAMESPACE) --dry-run=client -o yaml | oc apply -f -
	helm upgrade --install code-understanding ./helm \
		--set registry=$(REGISTRY) \
		--set version=$(VERSION) \
		--set namespace=$(NAMESPACE)

uninstall:
	helm uninstall code-understanding --namespace $(NAMESPACE)
	oc delete pvc workbench-data-generation-pvc workbench-data-indexing-pvc -n $(NAMESPACE) --ignore-not-found
