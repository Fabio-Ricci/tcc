import numpy as np

# Constants for the BASIC-2 adaptation scheme
BASIC_THRESHOLD = 10
BASIC_UPPER_THRESHOLD = 1.2
BASIC_DELTA_COUNT = 5

# Constants for the buffer occupation adaptation scheme
INSUFFICIENT_BUFFER_SAFETY_FACTOR = 0.5


class Dash():
    def __init__(self, bitrates, algorithm):
        self.algorithm = algorithm
        self.bitrates = bitrates
        self.current_bitrate = bitrates[0]
        self.average_dwn_time = 0.0
        self.segment_download_time = 0
        self.recent_download_sizes = []
        self.previous_segment_times = []
        self.previous_segment_times_seg = {}
        self.bitrates_seg = {}
        # variable for channel flow rate
        self.window_size = 5
        self.previous_download_times = np.zeros(self.window_size)
        self.previous_instant_flow_rates = np.zeros(self.window_size)

    def update_download_time(self, frame_download_time, segment):
        self.segment_download_time = frame_download_time
        self.previous_segment_times.append(frame_download_time)

        try:
            self.previous_segment_times_seg[segment] = self.previous_segment_times_seg[segment] + \
                frame_download_time
        except:
            self.previous_segment_times_seg[segment] = 0
            self.previous_segment_times_seg[segment] = self.previous_segment_times_seg[segment] + \
                frame_download_time

    def append_download_size(self, download_size):
        self.recent_download_sizes.append(download_size)

    def get_next_bitrate(self, segment_number):
        if self.algorithm == 'basic2':
            return self.basic_dash2(segment_number)
        elif self.algorithm == 'basic':
            return self.basic_dash(segment_number)
        elif self.algorithm == 'buffer_occupation':
            return self.buffer_occupation(segment_number)
        elif self.algorithm == 'channel_flow_rate':
            return self.channel_flow_rate(segment_number)
        elif self.algorithm == 'bola':
            return self.bola(segment_number)
        else:
            return self.current_bitrate

    def get_max_bitrate(self):
        self.current_bitrate = self.bitrates[-1]

        return self.current_bitrate

    def get_min_bitrate(self):
        self.current_bitrate = self.bitrates[0]

        return self.current_bitrate

    def basic_dash(self, segment_number):
        if self.average_dwn_time > 0 and segment_number > 0:
            updated_dwn_time = (self.average_dwn_time * (segment_number + 1) +
                                self.segment_download_time) / (segment_number + 1)
        else:
            updated_dwn_time = self.segment_download_time

        bitrates = [float(i) for i in self.bitrates]
        bitrates.sort()
        try:
            sigma_download = self.average_dwn_time / self.segment_download_time
        except ZeroDivisionError:
            self.bitrates_seg[segment_number] = self.current_bitrate
            self.average_dwn_time = updated_dwn_time
            return self.current_bitrate

        try:
            curr = bitrates.index(self.current_bitrate)
        except ValueError:
            if self.current_bitrate < bitrates[0]:
                curr = bitrates[0]
            elif self.current_bitrate > bitrates[-1]:
                curr = bitrates[-1]
            else:
                for bitrate, index in enumerate(bitrates[1:]):
                    if bitrates[index-1] < self.current_bitrate < bitrate:
                        curr = self.current_bitrate

        next_rate = self.current_bitrate
        if sigma_download < 1:
            if curr > 0:
                if sigma_download < bitrates[curr - 1]/bitrates[curr]:
                    next_rate = bitrates[0]
                else:
                    next_rate = bitrates[curr - 1]
        elif self.current_bitrate < bitrates[-1]:
            if sigma_download >= bitrates[curr - 1]/bitrates[curr]:
                temp_index = curr
                while next_rate < bitrates[-1] or sigma_download < (bitrates[curr+1] / bitrates[curr]):
                    temp_index += 1
                    next_rate = bitrates[temp_index]

        self.bitrates_seg[segment_number] = next_rate
        self.average_dwn_time = updated_dwn_time
        self.current_bitrate = next_rate
        return next_rate

    def basic_dash2(self, segment_number):
        # Truncating the list of download times and segment
        pst = self.previous_segment_times.copy()
        while len(pst) > BASIC_DELTA_COUNT:
            pst.pop(0)

        rds = self.recent_download_sizes.copy()
        while len(rds) > BASIC_DELTA_COUNT:
            rds.pop(0)

        if len(pst) == 0 or len(rds) == 0:
            self.bitrates_seg[segment_number] = self.bitrates[0]
            self.average_dwn_time = None
            self.current_bitrate = self.bitrates[0]
            return self.bitrates[0]

        updated_dwn_time = sum(self.previous_segment_times) / \
            len(self.previous_segment_times)

        # Calculate the running download_rate in Kbps for the most recent segments
        download_rate = sum(self.recent_download_sizes) * 8 / \
            (updated_dwn_time * len(self.previous_segment_times))
        bitrates = [float(i) for i in self.bitrates]
        bitrates.sort()
        next_rate = bitrates[0]

        # Check if we need to increase or decrease bitrate
        if download_rate > self.current_bitrate * BASIC_UPPER_THRESHOLD:
            # Increase rate only if  download_rate is higher by a certain margin
            # Check if the bitrate is already at max
            if self.current_bitrate == bitrates[-1]:
                next_rate = self.current_bitrate
            else:
                # if the bitrate is not at maximum then select the next higher bitrate
                try:
                    current_index = bitrates.index(self.current_bitrate)
                    next_rate = bitrates[current_index + 1]
                except ValueError:
                    current_index = bitrates[0]
        else:
            # If the download_rate is lower than the current bitrate then pick the most suitable bitrate
            for index, bitrate in enumerate(bitrates[1:], 1):
                if download_rate > bitrate * BASIC_UPPER_THRESHOLD:
                    next_rate = bitrate
                else:
                    next_rate = bitrates[index - 1]
                    break

        self.bitrates_seg[segment_number] = next_rate
        self.average_dwn_time = updated_dwn_time
        self.current_bitrate = next_rate
        return next_rate

    # map calculated_bitrate to one of the available bitrates (rounding down)
    def map_bitrate_to_available_bitrates(self, calculated_bitrate):
        bitrates = [float(i) for i in self.bitrates]
        bitrates.sort()

        curr_bitrate = self.bitrates[0]
        for _, bitrate in enumerate(bitrates[1:], 1):
            if calculated_bitrate <= bitrate:
                curr_bitrate = bitrate
            else:
                break

        return curr_bitrate

    def buffer_occupation(self, throughput, buffer_level, segment_duration):
        # buffer occupation formula
        calculated_bitrate = throughput * \
            (buffer_level/segment_duration) * INSUFFICIENT_BUFFER_SAFETY_FACTOR

        self.current_bitrate = self.map_bitrate_to_available_bitrates(
            calculated_bitrate)

        return self.current_bitrate

    def channel_flow_rate(self, last_segment_download_time, last_instant_flow_rate):
        # save new last segment download time
        self.previous_download_times = np.roll(
            self.previous_download_times, 1)  # rotate left
        self.previous_download_times[0] = 0
        self.previous_download_times[self.window_size -
                                     1] = last_segment_download_time

        # save new last instant flow rate
        self.previous_instant_flow_rates = np.roll(
            self.previous_instant_flow_rates, 1)  # rotate left
        self.previous_instant_flow_rates[0] = 0
        self.previous_instant_flow_rates[self.window_size -
                                         1] = last_instant_flow_rate

        # previous alpha fasts
        alpha_fasts = 0.5**self.previous_download_times
        # previous alpha slows
        alpha_slows = 0.5**(self.previous_download_times/2)
        # previous mi fasts
        mi_fasts = np.zeros(self.window_size)
        for i in range(1, self.window_size):
            mi_fasts[i] = (
                1-alpha_fasts[i])*self.previous_instant_flow_rates[i]+alpha_fasts[i]*mi_fasts[i-1]
        # previous mi slows
        mi_slows = np.zeros(self.window_size)
        for i in range(1, self.window_size):
            mi_slows[i] = (
                1-alpha_slows[i])*self.previous_instant_flow_rates[i]+alpha_slows[i]*mi_slows[i-1]

        # get min between last mi slow and mi fast
        bitrate = min(mi_slows[self.window_size-1],
                      mi_fasts[self.window_size-1])
        self.current_bitrate = self.map_bitrate_to_available_bitrates(bitrate)

        return self.current_bitrate

    def bola(self, segment_number):
        return self.current_bitrate
