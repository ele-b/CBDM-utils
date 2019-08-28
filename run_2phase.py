#!/usr/bin/env python3

from __future__ import print_function
import os
import subprocess
import argparse

nproc_cmd = 'sysctl -n hw.ncpu'
proc = subprocess.Popen(nproc_cmd, shell=True, stdout=subprocess.PIPE)
nproc = int(proc.communicate()[0])


def getArgs():
    parser = argparse.ArgumentParser(description='Create illuminance profiles with the 2-phase method')
    parser.add_argument('oct', type=str,
                        help='oct file path')
    parser.add_argument('clim', type=str,
                        help='climate file path (epw or wea)')
    parser.add_argument('opt', type=str,
                        help='ambient parameters options file path')
    parser.add_argument('pts', type=str, nargs='+',
                        help='sensor points list file path, multiple entries allowed')
    parser.add_argument('-mf', type=int, default=2,
                        help='sky subdivision factor')
    parser.add_argument('-ts', type=int, default=60,
                        help='time step (minutes)')
    parser.add_argument('-r', type=int, default=0,
                        help='sky rotation (degrees west of north)')
    parser.add_argument('--irr', action='store_true', default=False,
                        help='calculate irradiance profile')
    parser.add_argument('--direct', action='store_true', default=False,
                        help='calculate direct illuminance profile')
    args = parser.parse_args()

    direct = args.direct
    print('Direct calculation:', direct)
    irr = args.irr
    print('Irradiance calculation:', irr)

    return args


def makesmx(clim_fn, mf, ts=60, north=0, irr=False, direct=False):
    mf = int(mf)

    if not os.path.exists('temp'):
        os.makedirs('temp')

    clim, clim_ext = os.path.splitext(clim_fn)
    clim = os.path.basename(clim)

    if clim_ext == '.epw':
        wea = 'epw2wea %s temp/%s.wea' % (clim_fn, clim)
        os.system(wea)
    if clim_ext == '.wea':
        os.rename(clim_fn, 'temp/%s.wea' % clim)

    if irr:
        if direct:
            smx = 'gendaymtx -of -d -m %d -r %d -O1 temp/%s.wea | rmtxop -c .33 .33 .34 - > temp/%s-t%d-MF%d-d.smx' % (
                mf, north, clim, clim, ts, mf)
            smx_fp = 'temp/%s-t%d-MF%d-d.smx' % (clim, ts, mf)
        else:
            smx = 'gendaymtx -of -m %d -r %d -O1 temp/%s.wea | rmtxop -c .33 .33 .34 - > temp/%s-t%d-MF%d.smx' % (
                mf, north, clim, clim, ts, mf)
            smx_fp = 'temp/%s-t%d-MF%d.smx' % (clim, ts, mf)
    else:
        if direct:
            smx = 'gendaymtx -of -d -m %d -r %d temp/%s.wea | rmtxop -c 47.4 119.9 11.6 - > temp/%s-t%d-MF%d-d.smx' % (
                mf, north, clim, clim, ts, mf)
            smx_fp = 'temp/%s-t%d-MF%d-d.smx' % (clim, ts, mf)
        else:
            smx = 'gendaymtx -of -m %d -r %d temp/%s.wea | rmtxop -c .27 .66 .07 - > temp/%s-t%d-MF%d.smx' % (
                mf, north, clim, clim, ts, mf)
            smx_fp = 'temp/%s-t%d-MF%d.smx' % (clim, ts, mf)

    os.system(smx)

    return smx_fp


def run_2ph(oct, opt_fn, pts_fn, smx_fp, mf=2, ts=60, r=0, irr=False, direct=False):
    prj = os.path.splitext(oct)[0]
    print(prj)

    nhyear = (60 / ts) * 24 * 365
    assert (ts % 60 == 0) & (ts / 60 >= 1), 'The timestep should be 60 minutes or a submultiple of 60'

    with open(opt_fn, 'r') as f:
        opt = f.read()
        print(opt)

    if not os.path.exists('dc'):
        os.makedirs('dc')
    if not os.path.exists('res'):
        os.makedirs('res')
    if not os.path.exists('temp'):
        os.makedirs('temp')

    groundglow = '#@rfluxmtx h=u u=Y\nvoid glow ground_glow 0 0 4 1 1 1 0\nground_glow source ground 0 0 4 0 0 -1 180\n'
    skyglow = '#@rfluxmtx h=r%d u=Y\nvoid glow sky_glow 0 0 4 1 1 1 0\nsky_glow source sky 0 0 4 0 0 1 180\n' % mf
    with open('temp/whitesky.rad', 'w') as f:
        f.write(groundglow)
        f.write(skyglow)

    for wp_fp in pts_fn:
        line_n_cmd = 'wc -l < %s' % wp_fp
        proc = subprocess.Popen(line_n_cmd, shell=True, stdout=subprocess.PIPE)
        sen_n = int(proc.communicate()[0])
        print('Number of sensor points: %d' % sen_n)

        wp = os.path.basename(wp_fp)
        wp = os.path.splitext(wp)[0]

        if direct:
            bounces = '-ab 1'
            dc_fn = 'dc/%s-%s-MF%d-d.dc' % (prj, wp, mf)
            res_fn = 'res/%s-%s-MF%d-t%s-%03d-d' % (prj, wp, mf, ts, r)
        else:
            bounces = ''
            dc_fn = 'dc/%s-%s-MF%d.dc' % (prj, wp, mf)
            res_fn = 'res/%s-%s-MF%d-t%s-%03d' % (prj, wp, mf, ts, r)

        if irr:
            if not os.path.exists(dc_fn):
                rfluxmtx = 'rfluxmtx -faf -n %d @%s %s -I+ -y %d < %s - temp/whitesky.rad -i %s.oct | rmtxop -c .33 .33 .34 - > %s' % (
                    nproc, opt_fn, bounces, sen_n, wp_fp, prj, dc_fn)
                os.system(rfluxmtx)
            else:
                print('Existing DC matrix used for the simulation')

            rmtxop = 'rmtxop %s %s | rmtxop -fa - > %s.irr' % (dc_fn, smx_fp, res_fn)
        else:
            if not os.path.exists(dc_fn):
                rfluxmtx = 'rfluxmtx -faf -n %d @%s %s -I+ -y %d < %s - temp/whitesky.rad -i %s.oct | rmtxop -c .27 .66 .07 - > %s' % (
                    nproc, opt_fn, bounces, sen_n, wp_fp, prj, dc_fn)
                os.system(rfluxmtx)
            else:
                print('Existing DC matrix used for the simulation')

            rmtxop = 'rmtxop %s %s | rmtxop -fa -s 179 - > %s.ill' % (dc_fn, smx_fp, res_fn)
        os.system(rmtxop)

    for f in os.listdir('dc'):
        if os.path.getsize('dc/%s' % f) is 0:
            print('dc/%s is empty and will be removed' % f)
            os.remove('dc/%s' % f)

        for f in os.listdir('res'):
            if os.path.getsize('res/%s' % f) is 0:
                print('res/%s is empty and will be removed' % f)
                os.remove('res/%s' % f)

    return res_fn


if __name__ == "__main__":
    args = getArgs()
    print(args)
    smx_fp = makesmx(args.clim, args.mf, args.ts, args.r, args.irr, args.direct)
    run_2ph(args.oct, args.opt, args.pts, smx_fp, args.mf, args.ts, args.r, args.irr, args.direct)
