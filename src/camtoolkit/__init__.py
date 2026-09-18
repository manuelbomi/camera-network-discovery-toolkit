"""camtoolkit - camera network discovery and site-survey toolkit.

This package provides a small set of tools a solution engineer runs during
a technical site survey, before designing a video / AI architecture:

- ``discovery``: ONVIF WS-Discovery (UDP multicast) to find cameras on the LAN.
- ``manual_inventory``: load a YAML file of known cameras when discovery is
  not possible on the customer network.
- ``rtsp_health``: connect to a camera's RTSP stream and measure latency,
  achieved FPS, and resolution.
- ``network_readiness``: check that the ports and latency an architecture
  will depend on are actually usable on site.
- ``report``: combine all of the above into a CSV / JSON / HTML report.
"""

__version__ = "0.1.0"
