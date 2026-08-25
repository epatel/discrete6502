cmake_minimum_required(VERSION 3.13)
set(PICO_BOARD pico2_w CACHE STRING "Board type")
include(${CMAKE_CURRENT_LIST_DIR}/../common/pico_sdk_import.cmake)
project(discrete6502_wifi C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

# Credentials normally come from the captive portal and live in flash, so a
# plain build needs none. They remain available as an optional one-time seed for
# a board you want to arrive already provisioned; they still have no defaults,
# so nothing can be committed by accident:
#     cmake -B build -DWIFI_SSID=yournet -DWIFI_PASSWORD=secret
set(WIFI_SSID "" CACHE STRING "optional: pre-seed the stored network name")
set(WIFI_PASSWORD "" CACHE STRING "optional: pre-seed the stored password")
if(WIFI_SSID STREQUAL "")
    message(STATUS "wifi: no build-time credentials; the setup portal will run "
                   "on first boot (join \"discrete6502-setup\")")
endif()

include(${CMAKE_CURRENT_LIST_DIR}/../common/embed_functest.cmake)
add_executable(wifi main.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/bus6502.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/functest.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/ihex.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/retention.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/settings.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/netsrv.c)
discrete6502_add_functest_images(wifi)
target_include_directories(wifi PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/../common
    ${CMAKE_CURRENT_LIST_DIR})
target_compile_definitions(wifi PRIVATE
    WIFI_SSID=\"${WIFI_SSID}\"
    WIFI_PASSWORD=\"${WIFI_PASSWORD}\")
target_link_libraries(wifi
    pico_stdlib
    pico_multicore
    pico_cyw43_arch_lwip_poll
    pico_flash)
pico_enable_stdio_usb(wifi 1)
pico_enable_stdio_uart(wifi 0)
pico_add_extra_outputs(wifi)
