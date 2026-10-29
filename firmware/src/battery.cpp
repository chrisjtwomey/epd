#include "battery.h"

#include <math.h>

struct BatteryCapacity {
    double voltage;
    int percentage;
};

/**
 * The discharge curve of a 3.7 V 2000 mAh LiPo cell, as an Inkplate's
 * readBattery() sees it.
 *
 * Recorded in one run, at a steady 40 mA load, from a full charge (4.23 V) to
 * 3.0 V: the percent is the share of the run's time still to come. 0% sits at
 * 3.40 V, not at the cell's cut-off: below about 3.4 V the panel's power chip
 * can fail to start, so the board wakes but cannot draw.
 *
 * The curve is one cell's. For a closer fit to another cell, record its
 * discharge and put its rows here.
 */
static const BatteryCapacity capacityTable[] = {
    {4.230, 100}, {4.198, 99}, {4.179, 98}, {4.169, 97}, {4.154, 96}, {4.145, 95},
    {4.132, 94}, {4.127, 93}, {4.119, 92}, {4.108, 91}, {4.102, 90}, {4.098, 89},
    {4.092, 88}, {4.085, 87}, {4.082, 86}, {4.078, 85}, {4.076, 84}, {4.073, 83},
    {4.067, 82}, {4.060, 81}, {4.052, 80}, {4.049, 79}, {4.041, 78}, {4.034, 77},
    {4.027, 76}, {4.023, 75}, {4.015, 74}, {4.005, 73}, {3.998, 72}, {3.989, 71},
    {3.980, 70}, {3.974, 69}, {3.972, 68}, {3.964, 67}, {3.955, 66}, {3.950, 65},
    {3.944, 64}, {3.935, 63}, {3.925, 62}, {3.920, 61}, {3.911, 60}, {3.902, 59},
    {3.894, 58}, {3.886, 57}, {3.878, 56}, {3.872, 55}, {3.870, 54}, {3.865, 53},
    {3.856, 52}, {3.849, 51}, {3.846, 50}, {3.834, 49}, {3.826, 48}, {3.821, 47},
    {3.814, 46}, {3.802, 45}, {3.794, 44}, {3.782, 43}, {3.772, 42}, {3.768, 41},
    {3.758, 40}, {3.748, 39}, {3.744, 38}, {3.736, 37}, {3.726, 36}, {3.720, 35},
    {3.716, 34}, {3.710, 33}, {3.703, 32}, {3.697, 31}, {3.691, 30}, {3.684, 29},
    {3.677, 28}, {3.673, 27}, {3.670, 26}, {3.666, 25}, {3.658, 24}, {3.652, 23},
    {3.645, 22}, {3.641, 21}, {3.636, 20}, {3.627, 19}, {3.619, 18}, {3.616, 17},
    {3.607, 16}, {3.596, 15}, {3.588, 14}, {3.576, 13}, {3.568, 12}, {3.561, 11},
    {3.549, 10}, {3.537, 9}, {3.529, 8}, {3.523, 7}, {3.517, 6}, {3.514, 5},
    {3.507, 4}, {3.495, 3}, {3.478, 2}, {3.446, 1}, {3.400, 0},
};

static const int numCapacityEntries = sizeof(capacityTable) / sizeof(BatteryCapacity);

int batteryPercent(double voltage) {
    if (voltage >= capacityTable[0].voltage) return capacityTable[0].percentage;
    for (int i = 1; i < numCapacityEntries; i++) {
        const BatteryCapacity& above = capacityTable[i - 1];
        const BatteryCapacity& below = capacityTable[i];
        if (voltage >= below.voltage) {
            double share = (voltage - below.voltage) / (above.voltage - below.voltage);
            return (int)lround(below.percentage + share * (above.percentage - below.percentage));
        }
    }
    return 0;
}
