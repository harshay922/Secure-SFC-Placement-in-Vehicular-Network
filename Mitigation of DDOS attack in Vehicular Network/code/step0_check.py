# =====================================================================
# step0_check.py  -  STEP 0: check that every input file is present
# ---------------------------------------------------------------------
# Run:  python step0_check.py      (from inside the 'code' folder)
# It does NOT simulate anything. It only:
#   1) checks every file listed in config.py exists,
#   2) prints the main settings so you can confirm them,
#   3) lists the settings still marked [PENDING].
# =====================================================================

import os                      # to check whether files exist
import config as cfg           # our settings file (config.py in the same folder)

print("=" * 60)                                        # a line of '=' to make the output readable
print("STEP 0 - input file check")                     # title
print("=" * 60)

files_to_check = {                                     # a dictionary: short name -> full path from config.py
    "SUMO config": cfg.SUMO_CFG_FILE,
    "Road network": cfg.NET_FILE,
    "Car trips": cfg.TRIPS_FILE,
    "RSU list": cfg.RSU_FILE,
    "RSU links": cfg.LINK_FILE,
    "Alibaba containers": cfg.ALIBABA_CONTAINER_FILE,
    "Alibaba machines": cfg.ALIBABA_MACHINE_FILE,
}

all_ok = True                                          # becomes False if any file is missing
for name, path in files_to_check.items():              # go through every file one by one
    exists = os.path.isfile(path)                      # True if the file is really there
    size_kb = os.path.getsize(path) / 1024 if exists else 0   # file size in KB (0 if missing)
    status = "OK     " if exists else "MISSING"        # text to print
    print(f"{status} {name:20s} {size_kb:10.1f} KB   {os.path.basename(path)}")   # one line per file
    all_ok = all_ok and exists                         # remember if something is missing

os.makedirs(cfg.RESULTS_DIR, exist_ok=True)            # create the results folder if it does not exist yet
print(f"\nResults folder: {cfg.RESULTS_DIR}")           # show where outputs will be saved

print("\n--- main settings ---")                        # print the key numbers so you can confirm them
print(f"Simulation length      : {cfg.SIM_DURATION_S} s, seeds {cfg.SEEDS}")
print(f"RSU range / offload    : {cfg.RSU_RANGE_M} m / max {cfg.MAX_OFFLOAD_HOPS} hops")
print(f"Normal requests        : lambda = {cfg.LAMBDA_NORMAL}/s, SFC length {cfg.SFC_LEN_MIN}-{cfg.SFC_LEN_MAX}, {cfg.NUM_VNF_TYPES} VNF types, {int(cfg.SAFETY_SHARE*100)}% safety")
print(f"Attack                 : {int(cfg.ATTACKER_SHARE*100)}% cars, lambda = {cfg.LAMBDA_ATTACK}/s, size x{cfg.ATTACK_SIZE_FACTOR}, hold x{cfg.ATTACK_HOLD_FACTOR}, {int(cfg.ATTACK_FAKE_SAFETY_SHARE*100)}% fake safety")
print(f"Detection              : phi_min = {cfg.PHI_MIN}, report every {cfg.REPORT_INTERVAL_S} s, recover after {cfg.RECOVERY_HEALTHY_S} s healthy")
print(f"Safety reserve         : {int(cfg.SAFETY_RESERVE_SHARE*100)}% (only on flagged RSUs)")
print(f"Migration              : target = {cfg.MIGRATION_TARGET}, delay = {cfg.MIGRATION_DELAY_MS} ms")
print(f"Schemes                : {list(cfg.SCHEMES.keys())}")

print("\n--- settings still PENDING (waiting for your answer) ---")
with open(os.path.join(cfg.CODE_DIR, "config.py")) as f:   # open config.py as plain text
    for line in f:                                     # read it line by line
        if "[PENDING" in line:                         # keep only lines marked PENDING
            print("  " + line.strip())                 # print them without extra spaces

print("\nRESULT:", "all input files found - Step 0 OK" if all_ok else "some files are MISSING - fix before Step 1")
