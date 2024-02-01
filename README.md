# bootloader-gui

BOOT Flasher: a PySide6 desktop GUI for the NUCLEO-F767ZI A/B bootloader. It builds and flashes [BOOT](https://github.com/soccentric-stm32/bootloader) over SWD, and clones, builds, signs and uploads the seven firmware projects through BOOT.

[![BOOT Flasher: clone, build, sign and flash from one window](https://raw.githubusercontent.com/soccentric-stm32/soccentric-stm32.github.io/main/assets/shots/bootloader-gui.webp)](https://soccentric-stm32.github.io/#bootloader-gui)

## Requirements

- A checkout of the [bootloader](https://github.com/soccentric-stm32/bootloader) repository: next to this one (`../bootloader`) in a flat workspace, or in the `bootloader/` group folder of the full workspace. Set `BOOTLOADER_DIR` to use another checkout. The GUI runs its `tools/bootctl.py`, `tools/mkimage.py`, `scripts/docker-dev.sh` and `keys/`.
- Python 3.10+ with PySide6, pyserial and cryptography (`make deps`).
- For flashing: the `stm32-dev` Docker image, or OpenOCD on the host.

## Pages

- **Bootloader**: build BOOT and program it over SWD, in the container or with host tools. Host builds need STM32CubeF7 (`STM32CUBE_F7`) and use `build-host/`, kept apart from the container's `build/`; the GUI falls back to Docker when the SDK is missing. Probe, reset, provision and erase are shown as buttons under the build row.
- **Applications**: app-c-freertos, app-c-zephyr, app-rust-embassy, app-rust-freertos, app-rust-zephyr, factory-firmware and validation-firmware. Each is cloned if missing, built, signed with `mkimage.py --sign` and uploaded with `bootctl.py update --activate --wait`. Signing is offline: “Match board” uses the floor shown in the Board panel when it is known, otherwise the image keeps its own counter, so an application that does not answer HWLINK cannot fail a signature.
- **Board panel**: BOOT's version, slots, trusted key and security floor, checked before flashing.
- **Debug terminal**: the firmware's USART6 debug output (PG14 / Arduino D1, 115200 8N1) on the right, with its own port selector — normally a USB-serial adapter such as `/dev/ttyUSB0`; the ST-LINK VCP carries HWLINK. It stays live while bootctl flashes or reads the board when the debug port is a different device, and only pauses if you select the same port. Close it with its × button or `Ctrl+J`; reopen it from `View > Debug Terminal` or the terminal button above the output console.
- **Recover Board into BOOT**: reaches BOOT when the running application does not answer HWLINK.

## Run

```bash
make deps     # one-time
make gui      # launch
make test     # Python tests
make package  # desktop package for this OS (packaging/README.md)
```

Shortcuts: `Ctrl+1`..`Ctrl+6` pages, `Ctrl+Enter` run the whole pipeline, `Ctrl+B` build, `Ctrl+Shift+Enter` flash only, `Esc` cancel, `F5` refresh the board, `Ctrl+R` reset, `Ctrl+K` clear the output, `Ctrl+J` show or hide the debug terminal.

## Environment

| Variable | Meaning |
|---|---|
| `BOOTLOADER_DIR` | Bootloader repository (default `../bootloader`) |
| `FIRMWARE_WORKSPACE` | Workspace holding the firmware repositories. Default: the nearest parent with `repos.yaml`, where each repository is at `<group>/<name>` (for example `applications/app-c-zephyr`); otherwise the parent directory, flat |
| `BOOT_SIGNING_KEY` | Signing key (default: the bootloader's development key) |

## Layout

`flash_gui.py` is the entry point; `gui/` holds `window.py`, `pages.py`, `projects.py` (the project list), `runner.py`, `device.py`, `terminal.py` (the debug UART monitor), `widgets.py`, `theme.py` and `icons.py`. `theme.py` is the reference SoCcentric theme (tokens, fonts, light/dark, the one style sheet) and is copied byte-identically into Factory Data, HWVAL Studio and HWVAL Factory.

## License

MIT, see [LICENSE](LICENSE).
