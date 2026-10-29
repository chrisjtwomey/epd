#ifndef EPD_BATTERY_H
#define EPD_BATTERY_H
/**
  The charge left in the battery, in percent, at ``voltage``: blended between
  the two nearest rows of the discharge curve of a 3.7 V 2000 mAh LiPo cell.
  0% is 3.40 V, where an Inkplate's panel stops drawing.
*/
int batteryPercent(double voltage);
#endif