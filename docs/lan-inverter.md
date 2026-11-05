# LAN inverter

Site notes from [SolarEdge inverter integration](a469d439-4233-4a78-9e1b-151f0e469fd2) (17 August 2026), updated 23 October 2026 after the LAN address moved. The exporter reaches this inverter over Ethernet Modbus TCP. Cloud SolarEdge monitoring stays on. It uses a different path.

## This inverter

LCD unit. Identity from the 17 August status screen:

| Field | Value |
| :--- | :--- |
| ID | `7315A571 9E` |
| DSP1/2 | `1.0000/2.0000` |
| CPU | `3.2221` |
| Country | `USA3` |
| Server | `LAN` |
| Status | `11111111` |
| Mask | `255.255.252.0` (`/22`, `192.168.4.0–192.168.7.255`) |
| Gateway | `192.168.4.1` |
| MAC | `0-27-02-15-A5-71` |
| ZigBee | none |

CPU `3.2221` is the same 3.x firmware the exporter was tested against (`SE5000` / `3.2221.0`). `DSP1/2` does not decide SunSpec support. `Status: 11111111` was read as no faults. `Server: LAN` means the portal connection stays as it is.

The Docker host that runs Compose must sit on that LAN, or have a route into `192.168.4.0/22`. On 23 October 2026 this Mac still used gateway `192.168.4.1` on `en0`, and `ping -c 3 192.168.4.1` succeeded.

## Why the IP changed

On 17 August 2026 the LCD showed `192.168.4.21`. Ping from this host succeeded (3 packets, 0% loss, about 7.2–7.8 ms, TTL 64) and TCP 502 was open.

On 23 October 2026 the LCD showed a different address. From this same Mac:

- `ping -c 3 192.168.4.21` lost all 3 packets
- TCP `192.168.4.21:502` timed out
- The kernel route for `192.168.4.21` was an expired ARP entry on `en0`
- The gateway `192.168.4.1` still answered

`192.168.4.21` was a DHCP lease from the router at `192.168.4.1`, not an address the inverter owns. The LCD that day showed a normal DHCP client: an address in the router subnet, mask `/22`, gateway `.1`. SolarEdge's cloud portal does not assign this address. Turning Modbus TCP on does not change it. The exporter does not change it.

A home router lends an address for a lease, often a day to a week, and the client can renew that same address for a long time. The lease is not a permanent assignment. Between 17 August and 23 October there were many lease cycles. The address moves when any of these happen:

1. The router reboots or loses its lease table (power cut, firmware update) and offers a new address the next time the inverter asks.
2. The inverter is offline long enough for the lease to expire (power cycle, Ethernet unplug, or a long outage). The router may then give `192.168.4.21` to another device. When the inverter returns and requests `.21`, the router refuses and offers a different address.
3. Another client already holds `.21`. The 23 October check matches that shape: the gateway answers, `.21` answers neither ARP, ICMP, nor TCP, and the LCD has moved on.

The stable identifier on the LAN is the MAC `0-27-02-15-A5-71`. To stop the address moving, create a DHCP reservation on `192.168.4.1` for that MAC, or set a static address on the inverter in `192.168.4.0/22` outside the router's DHCP pool. Until then, read the IP from the LCD and put that value in `INVERTER_ADDRESS` before `docker compose up`.

The current LCD IP is not recorded in this note. `INVERTER_ADDRESS` in `.env` is the address the exporter uses. Read the LCD again when that address stops answering.

## Compose values

```text
INVERTER_ADDRESS=<current LCD IP>
INVERTER_PORT=502
NUMBER_METERS=0
INVERTER_CLIENT_ID=1
```

LCD Modbus uses port **502** and device ID **1**. The inverter allows one Modbus TCP client. Stop Home Assistant, another logger, or a GUI tester before this exporter connects. The exporter polls every 5 seconds, inside the inverter's 2-minute idle timeout.

## Enable Modbus TCP

Modbus TCP is off until enabled. On this LCD unit:

1. Long-press **Enter/OK**. The installer code is typically `12312312`.
2. **Communication → LAN Conf → Modbus TCP → Enable**.
3. Leave the port at **502**.
4. Leave the device ID at **1**.
5. Short-press the light button until the Modbus screen shows the current IP, port **502**, and status **Ready**.

| Status | Meaning |
| :--- | :--- |
| Init | Server starting, about 10 seconds after the first enable |
| Ready | Listening |
| Connected | Another client already holds the only session |
| Failed | See the error on screen |
| Disconnected | No Ethernet cable |
| Gateway Ping Failed | Router unreachable |
| No IP | DHCP or static address missing |

A SetApp inverter uses **Commissioning → Site Communication → Modbus TCP → Enable** and defaults to port **1502**. This unit is LCD, so the port stays **502**.

## Reachability

From a machine on the LAN, using the IP on the LCD that day:

```bash
ping -c 3 <lcd-ip>
nc -vz <lcd-ip> 502
```

If `nc` is missing:

```bash
python3 -c "import socket; s=socket.create_connection(('<lcd-ip>',502),3); print('open'); s.close()"
```

Ping to the gateway with a timeout to the LCD address means the inverter is no longer at that address. Read the LCD again. A ping that works and a refused connection on 502 means Modbus TCP is still disabled.

## What the path can and cannot use

Ethernet carries both the SolarEdge portal session and SunSpec Modbus TCP. ZigBee, GSM, and cellular cannot carry Modbus TCP. Wi-Fi to the SolarEdge server is a cloud path. The exporter needs the inverter's Ethernet address.

SunSpec support on an LCD inverter requires CPU firmware **3.xxxx** or newer. A `2.xxxx` CPU needs a firmware upgrade first. SetApp-commissioned inverters support SunSpec, and still need Modbus TCP enabled on Ethernet.

The exporter reads SunSpec model **101** (single-phase), **102** (split-phase), or **103** (three-phase). This SE3800 reported model `SE3800`, serial `7315A571`, and firmware `0003.2221`, and meter 1 is not enabled, so `NUMBER_METERS` stays `0`. Raise it when a meter is installed. Confirm a live scrape with `SunSpec_DID` of 101, 102, or 103 and a numeric `AC_Power`. At night `AC_Power` may be near zero.

Official reference: [SunSpec Implementation Technical Note v3.2 (June 2025)](https://knowledge-center.solaredge.com/sites/kc/files/sunspec-implementation-technical-note.pdf).
