# discrete6502 Pico firmware builds.
#
#   make              build tester + general
#   make wifi         build the wifi firmware (needs credentials, see below)
#   make all-wifi     all three
#   make size         report flash/RAM use of whatever is built
#   make flash-tester flash a firmware over USB (hold BOOTSEL first)
#   make clean        remove the build directories
#
# Requires PICO_SDK_PATH and the ARM GCC toolchain — see README.md.

PROJECTS   := tester general wifi
BUILD      ?= build
BUILD_TYPE ?= Release
CMAKE      ?= cmake
JOBS       ?= $(shell sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
SIZE       ?= arm-none-eabi-size

# Optional, git-ignored: put WIFI_SSID / WIFI_PASSWORD here instead of typing
# them on the command line every time (and into your shell history).
#
#   $ cat wifi.local.mk
#   WIFI_SSID := yournet
#   WIFI_PASSWORD := secret
-include wifi.local.mk

.PHONY: all all-wifi $(PROJECTS) clean distclean size help check-sdk check-wifi

all: tester general

all-wifi: tester general wifi

help:
	@echo "targets: all (tester general), all-wifi, $(PROJECTS), size, clean, flash-<name>"
	@echo "wifi needs WIFI_SSID/WIFI_PASSWORD on the command line or in wifi.local.mk"

check-sdk:
	@test -n "$(PICO_SDK_PATH)" || { \
	  echo "PICO_SDK_PATH is not set."; \
	  echo "  export PICO_SDK_PATH=\$$HOME/Development/pico-sdk"; exit 1; }
	@test -d "$(PICO_SDK_PATH)" || { \
	  echo "PICO_SDK_PATH=$(PICO_SDK_PATH) does not exist."; exit 1; }

check-wifi:
	@test -n "$(WIFI_SSID)" -a -n "$(WIFI_PASSWORD)" || { \
	  echo "wifi needs credentials — they have no default so they cannot be committed:"; \
	  echo "  make wifi WIFI_SSID=yournet WIFI_PASSWORD=secret"; \
	  echo "or put them in wifi.local.mk (git-ignored)."; exit 1; }

# $(1) = project directory, $(2) = extra cmake defines
define build_project
	@$(CMAKE) -S $(1) -B $(1)/$(BUILD) -DCMAKE_BUILD_TYPE=$(BUILD_TYPE) $(2) >/dev/null
	@$(CMAKE) --build $(1)/$(BUILD) -j$(JOBS)
	@echo "-> $(1)/$(BUILD)/$(1).uf2"
endef

tester general: check-sdk
	$(call build_project,$@,)

wifi: check-sdk check-wifi
	$(call build_project,$@,-DWIFI_SSID='$(WIFI_SSID)' -DWIFI_PASSWORD='$(WIFI_PASSWORD)')

size:
	@found=0; for p in $(PROJECTS); do \
	  elf=$$p/$(BUILD)/$$p.elf; \
	  if [ -f "$$elf" ]; then found=1; echo "== $$p"; $(SIZE) "$$elf" | tail -1; fi; \
	done; \
	[ $$found = 1 ] || echo "nothing built yet"

# Flashing needs the Pico in BOOTSEL mode (hold the button while plugging USB).
flash-%:
	@test -f $*/$(BUILD)/$*.uf2 || { echo "build $* first: make $*"; exit 1; }
	@if command -v picotool >/dev/null 2>&1; then \
	  picotool load -f -x $*/$(BUILD)/$*.uf2; \
	else \
	  echo "picotool not found — copy this onto the RP2350 mass-storage volume:"; \
	  echo "  $(CURDIR)/$*/$(BUILD)/$*.uf2"; \
	fi

clean:
	@rm -rf $(foreach p,$(PROJECTS),$(p)/$(BUILD))
	@echo "removed build directories"

distclean: clean
