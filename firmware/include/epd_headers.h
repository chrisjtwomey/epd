#ifndef EPD_HEADERS_H
#define EPD_HEADERS_H

/**
  The names this contract uses on the wire.

  Each one is the product's prefix followed by what the header says, so
  anyone reading the traffic sees the product rather than the library it was
  built with. A project sets EPD_HEADER_PREFIX to its own name at build time.

  Header names are case-insensitive, so the spelling here is for the reader.
*/
#ifndef EPD_HEADER_PREFIX
#define EPD_HEADER_PREFIX "EPD"
#endif

#define EPD_HEADER(suffix) EPD_HEADER_PREFIX suffix

// The board says who it is and what it runs, on every request.
#define EPD_H_DEVICE          EPD_HEADER("-Device")
#define EPD_H_DEVICE_VERSION  EPD_HEADER("-Device-Version")

// The server answers with its own identity, on every response.
#define EPD_H_SERVER_VERSION  EPD_HEADER("-Server-Version")
#define EPD_H_SERVER_EPOCH    EPD_HEADER("-Server-Epoch-Seconds")

// What to do next, and what firmware is on offer.
#define EPD_H_NEXT_REFRESH    EPD_HEADER("-Next-Display-Refresh-Seconds")
#define EPD_H_NEXT_URL        EPD_HEADER("-Next-URL")
#define EPD_H_NEXT_SENSOR_POLL EPD_HEADER("-Next-Sensor-Poll-Seconds")
#define EPD_H_FIRMWARE_VERSION EPD_HEADER("-Server-Firmware-Version")
#define EPD_H_FIRMWARE_URL     EPD_HEADER("-Server-Firmware-URL")

#endif  // EPD_HEADERS_H
