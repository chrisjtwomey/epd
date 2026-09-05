#ifndef __SD_CONFIG_H__
#define __SD_CONFIG_H__

#include "settings.h"

/**
  Let the card's config.yaml override the config this image was built with.

  Anything wrong with the card is a warning that leaves cfg as it was, so the
  board draws its page from the settings it already has rather than blanking
  the panel until someone finds the card.

  @returns true when a card was found, which is also whether to keep the
  downloaded image on it.
*/
bool applySdConfig(ClientConfig* cfg);

#endif  // __SD_CONFIG_H__
