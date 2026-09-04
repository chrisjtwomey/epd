#ifndef __OTA_OFFER_H__
#define __OTA_OFFER_H__

/**
  Whether the server offered an image this board should take.

  True when there is somewhere to fetch it from and the version differs from
  the one running. The server decides who is eligible; this is only the
  client's check that the offer is complete and is not the running image.
*/
bool updateOffered(const char* runningVersion, const char* offeredVersion,
                   const char* offeredURL);

#endif  // __OTA_OFFER_H__
