from math import ceil

def heat_detectors_required(area):
    return max(1, ceil(area / 40))