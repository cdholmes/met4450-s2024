#!/usr/bin/env python3
'''Helpful functions for MET4450, MET5451 assignments
'''

import pandas as pd
import s3fs

# Connect to AWS public buckets
fs = s3fs.S3FileSystem(anon=True)

def _goes_file_df(satellite, product, start, end, bands=None, refresh=True):
    '''Get list of requested GOES files as pandas.DataFrame.

    Excerpted from Brian Blaylock's goes2go
    
    Parameters
    ----------
    satellite : str
    product : str
    start : datetime
    end : datetime
    band : None, int, or list
        Specify the ABI channels to retrieve.
    refresh : bool
        Refresh the s3fs.S3FileSystem object when files are listed.
        Default True will refresh and not use a cached list.
    
    Returns
    -------
    pandas.DataFrame
    '''

    params = locals()

    start = pd.to_datetime(start)
    end = pd.to_datetime(end)

    DATES = pd.date_range(f"{start:%Y-%m-%d %H:00}", f"{end:%Y-%m-%d %H:00}", freq="1h")

    # List all files for each date
    # ----------------------------
    files = []
    for DATE in DATES:
        files += fs.ls(f"{satellite}/{product}/{DATE:%Y/%j/%H/}", refresh=refresh)

    if len(files)==0:
        raise ValueError( f'No files found for \nSatellite: {satellite} \n'
                         +f'Product: {product} \nDates: {DATES}' )

    # Build a table of the files
    # --------------------------
    df = pd.DataFrame(files, columns=["file"])
    df[["product_mode", "satellite", "start", "end", "creation"]] = (
        df["file"].str.rsplit("_", expand=True, n=5).loc[:, 1:]
    )

    # Todo: this could use some clean up !
    if product.startswith("ABI"):
        product_mode = df.product_mode.str.rsplit("-", n=1, expand=True)
        df["product"] = product_mode[0]
        df["mode_bands"] = product_mode[1]

        mode_bands = df.mode_bands.str.split("C", expand=True)
        df["mode"] = mode_bands[0].str[1:].astype(int)
        try:
            df["band"] = mode_bands[1].astype(int)
        except:
            # No channel data
            df["band"] = None

        # Filter files by band number
        if bands is not None:
            if not hasattr(bands, "__len__"):
                bands = [bands]
            df = df.loc[df.band.isin(bands)]

    # Filter files by requested time range
    # ------------------------------------
    # Convert filename datetime string to datetime object
    df["start"] = pd.to_datetime(df.start, format="s%Y%j%H%M%S%f")
    df["end"] = pd.to_datetime(df.end, format="e%Y%j%H%M%S%f")
    df["creation"] = pd.to_datetime(df.creation, format="c%Y%j%H%M%S%f.nc")

    # Filter by files within the requested time range
    df = df.loc[df.start >= start].loc[df.end <= end].reset_index(drop=True)

    for i in params:
        df.attrs[i] = params[i]

    return df

def find_goes_dataset(satellite=16,
                  product='ABI-L2-MCMIP',
                  domain='C',
                  bands=None,
                  datetime=pd.Timestamp.now()):
    '''Get the path to GOES data on AWS
    
    Parameters
    ----------
    satellite : int {16,17,18}
        number of GOES satellite, 16 or 18 recommended (default=16)
    product : str
        name of the GEOS product (default='ABI-L2-MCMIP')
    domain : {'C' (default),'F','M1','M2'}
        satellite domain, C=CONUS; F=Full Disk; M1, M2 = Mesoscale 1 and 2
    bands : int or array_like
        ABI channel number or numbers, not needed for many products
    datetime : pandas.Timestamp, datetime.datetime, or str
        date and time of the requested product, default is most recent
    
    Returns
    -------
    df : pandas.DataFrame
        DataFrame containing info about the GOES file that best matches input criteria 
        * file : path and filename for GOES data
        * satellite : name of GOES satellite
        * product : name of GOES product
        * domain : name of GOES domain
        * band : band number or None for multispectral
        * start : start time of image acquisition
        * end : end time of image acquisition
        * creation : time of file creation 
    '''

    params = locals()

    #noaa-goes16/ABI-L2-MCMIPC/2019/172/18/OR_ABI-L2-MCMIPC-M6_G16_s20191721801547_e20191721804320_c20191721804433.nc'
    if str(satellite).upper() in ['16','G16','GOES16','GOES-16','GOES-EAST','EAST']:
        number = '16'
    elif str(satellite).upper() in ['17','G17','GOES17','GOES-17']:
        number = '17'
    elif str(satellite).upper() in ['18','G18','GOES18','GOES-18','GOES-WEST','WEST']:
        number = '18'
    else:
        raise ValueError( 'Satellite name not recognized: '+str(satellite) )

    bucket = 'noaa-goes'+number
    platform = 'G'+number

    # Convert to pandas Timestamp
    datetime = pd.Timestamp(datetime)

    if domain in ['M1','M2']:
        product_domain = product+'M'
    else:
        product_domain = product+domain

    # DataFrame of files within ± 1 hour of target time
    df = _goes_file_df(bucket,
                  product_domain,
                  datetime-pd.Timedelta('1h'),
                  datetime+pd.Timedelta('1h'),
                  bands=bands,
                  refresh=True)

    # For mesoscale domains, select just one
    if domain in ['M1','M2']:
        df = df.loc[df.product_mode.str.contains(product+domain),:]

    # Add info for product and domain
    df['product'] = product
    df['domain']  = domain

    # Get row that matches the nearest time
    df = df.sort_values("start")
    df = df.set_index(df.start)
    unique_times_index = df.index.unique()
    nearest_time_index = unique_times_index.get_indexer([datetime], method="nearest")
    nearest_time = unique_times_index[nearest_time_index]
    df = df.loc[nearest_time]
    df = df.reset_index(drop=True)

    # Alert if no files found
    n = len(df.file)
    if n == 0:
        print("🛸 No data....🌌")
        return None

    for i in params:
        df.attrs[i] = params[i]

    return df
