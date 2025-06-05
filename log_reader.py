import sys
import re
import datetime

if len(sys.argv) < 2:
    print("Usage: python script.py <keyword>")
    sys.exit(2)

arg = sys.argv[1].lower()
alarm_pattern = f"{arg}_alarm"
output_pattern = f"{arg}_output"
component = alarm_pattern.split("_")[0]

logfile = r"c:\\LEDMonitoring\\debug.log"

with open(logfile, encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

start_check_pattern = re.compile(
    r'(\d{4}[-/]\d{2}[-/]\d{2} \d{2}:\d{2}:\d{2}) \[INFO\] Starting check display_status',
    re.IGNORECASE,
)

# Find all start checks (index, timestamp)
start_checks = []
for i, line in enumerate(lines):
    m = start_check_pattern.search(line)
    if m:
        ts = (
            datetime.datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S")
            if "/" in m.group(1)
            else datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        )
        start_checks.append((i, ts))

if not start_checks:
    print(f"No start checks found for {component}.")
    sys.exit(4)

now = datetime.datetime.now()
latest_start_idx, latest_start_time = start_checks[-1]

if (now - latest_start_time).total_seconds() / 60 > 40:
    print(f"{component} check last started at {latest_start_time.strftime('%Y/%m/%d %H:%M:%S')} (>40 min ago). Exiting.")
    sys.exit(4)

alarm_re = re.compile(re.escape(alarm_pattern), re.IGNORECASE)
alarm1_re = re.compile(rf'{re.escape(arg)}_alarm=1', re.IGNORECASE)
alarm0_re = re.compile(rf'{re.escape(arg)}_alarm=0', re.IGNORECASE)
output_re = re.compile(re.escape(output_pattern), re.IGNORECASE)

last_port = [""]

def collect_alarms(start_idx, end_idx):
    alarms_1 = []
    alarms_0 = []
    for idx in range(start_idx, end_idx):
        line = lines[idx]
        m = re.search(r'opened device on port:\s*([a-zA-Z0-9]+)', line, re.IGNORECASE)
        if m:
            last_port[0] = m.group(1)

        if alarm_re.search(line):
            result = []

            # Find output line
            for next_line in lines[idx + 1 :]:
                if output_re.search(next_line):
                    output_line = next_line.strip()
                    prefix_pattern = re.compile(rf'^{re.escape(output_pattern)}=', re.IGNORECASE)
                    cleaned_output = prefix_pattern.sub("", output_line)
                    result.append(cleaned_output)
                    break
            while len(result) < 3:
                result.append("")

            if alarm1_re.search(line):
                alarms_1.append(result[:3])
            elif alarm0_re.search(line):
                alarms_0.append(result[:3])
    return alarms_1, alarms_0

# Collect alarms in latest check (to end of file)
alarms_1, alarms_0 = collect_alarms(latest_start_idx, len(lines))

if alarms_1:
    for block in alarms_1:
        print("\n".join(block))
    sys.exit(2)

if alarms_0:
    print(f"{component} OK.")
    sys.exit(0)

# No alarms found in recent check, try previous check
if len(start_checks) > 1:
    prev_start_idx = start_checks[-2][0]
    prev_start_time = start_checks[-2][1]
    alarms_1_prev, alarms_0_prev = collect_alarms(prev_start_idx, latest_start_idx)

    if alarms_1_prev:
        for block in alarms_1_prev:
            print("".join(block))
        sys.exit(2)
    if alarms_0_prev:
        print(f"{component} OK.")
        sys.exit(0)

# No alarms found anywhere
print(f"{component} OK.")
sys.exit(0)
