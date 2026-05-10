from math import ceil

def smoke_detectors_required(area):
    return max(1, ceil(area / 60))