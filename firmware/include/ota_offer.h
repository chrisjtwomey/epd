#ifndef __OTA_OFFER_H__
#define __OTA_OFFER_H__

/**
  Whether the server offered an image this board should take.

  True when there is somewhere to fetch it from, the version differs from the
  one running, and it is not the version this board already tried and rolled
  back from. The server decides who is eligible; this is the client's check
  that the offer is complete, new, and not known to be broken.

  Without the last check a bad release loops: roll back, be offered it again,
  take it again. Pass the version otaRollback() recorded, or an empty string.
*/
bool updateOffered(const char* runningVersion, const char* offeredVersion,
                   const char* offeredURL, const char* rejectedVersion);

/** Whether this is the image the board already tried and rolled back from. */
bool updateRefusedBefore(const char* offeredVersion, const char* rejectedVersion);

#endif  // __OTA_OFFER_H__
