#ifndef EPD_BATTERY_H
#define EPD_BATTERY_H
/**
  The charge left in the battery, in percent, at ``voltage``: blended between
  the two nearest rows of the discharge table of a 3.7 V 2000 mAh LiPo cell.
*/
int batteryPercent(double voltage);
#endif