# Tactical Phosphor Radar Simulation

A real-time, multi-threaded Pygame visualization that emulates a vintage tactical phosphor radar screen. It intercepts live flight data from transponders via the OpenSky Network API to display real-world aircraft operating within a localized radar cell.

---

## System Architecture & Data Flow

 ┌────────────────────────────────────────────────────────┐
 │                 BACKGROUND API THREAD                  │
 │  1. Requests OAuth2 Token    2. Polls OpenSky API      │
 └─────────────────────────┬──────────────────────────────┘
                           │
                           ▼ (Filters by LAT/LON/RADIUS)
 ┌────────────────────────────────────────────────────────┐
 │                   SHARED API CACHE                     │
 │          Stores: ICAO, Pos, Alt, Speed, Type           │
 └─────────────────────────┬──────────────────────────────┘
                           │
                           ▼ (Thread-Safe Read)
 ┌────────────────────────────────────────────────────────┐
 │                   PYGAME MAIN LOOP                     │
 │  • Sweeps beam 12°/sec      • Calculates intersections │
 │  • Renders dynamic tracks   • Plays auditory 'ping'    │
 └────────────────────────────────────────────────────────┘

## Prerequisites & Dependencies

Before running the simulation, ensure you have the following installed on your host system:

* **Python 3.8 or higher**
* **Pygame** — For high-performance graphics rendering and audio execution.
* **Requests** — For handling synchronous OAuth2 token management and OpenSky REST API polling.

---