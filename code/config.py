default_config = {
    "signifiance_threshold":0.05,
    "beta_exclude_01s":False,
    "":"",
    "":"",
    "":"",
    "":"",
    "":"",
    "":"",

}

def get_config(filename=None):
    config = default_config
    if filename:
        with open(filename) as txt:
            for line in txt:
                row = line.rstrip().split('=')
                config[row[0]] = row[1]
    return config
