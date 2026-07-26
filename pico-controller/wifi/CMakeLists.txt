cmake_minimum_required(VERSION 3.13)
set(PICO_BOARD pico2_w CACHE STRING "Board type")
include(${CMAKE_CURRENT_LIST_DIR}/../common/pico_sdk_import.cmake)
project(discrete6502_wifi C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

# Credentials are build-time only and deliberately have no defaults, so they
# can never be committed: cmake -B build -DWIFI_SSID=... -DWIFI_PASSWORD=...
set(WIFI_SSID "" CACHE STRING "WiFi network name")
set(WIFI_PASSWORD "" CACHE STRING "WiFi password")
if(WIFI_SSID STREQUAL "" OR WIFI_PASSWORD STREQUAL "")
    message(FATAL_ERROR
        "set credentials: cmake -B build -DWIFI_SSID=yournet -DWIFI_PASSWORD=secret")
endif()

add_executable(wifi main.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/bus6502.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/functest.c
    ${CMAKE_CURRENT_LIST_DIR}/../common/ihex.c)
target_include_directories(wifi PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/../common
    ${CMAKE_CURRENT_LIST_DIR})
target_compile_definitions(wifi PRIVATE
    WIFI_SSID=\"${WIFI_SSID}\"
    WIFI_PASSWORD=\"${WIFI_PASSWORD}\")
target_link_libraries(wifi
    pico_stdlib
    pico_multicore
    pico_cyw43_arch_lwip_poll)
pico_enable_stdio_usb(wifi 1)
pico_enable_stdio_uart(wifi 0)
pico_add_extra_outputs(wifi)
