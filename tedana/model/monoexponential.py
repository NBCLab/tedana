"""
Functions to estimate S0 and T2* from multi-echo data.
"""
import logging

import numpy as np

from tedana import utils

logging.basicConfig(format='[%(levelname)s]: %(message)s', level=logging.INFO)
LGR = logging.getLogger(__name__)


def fit_decay(data, tes, mask, masksum, start_echo):
    """
    Fit voxel-wise monoexponential decay models to estimate T2* and S0 maps.

    Parameters
    ----------
    data : (S x E x T) array_like
        Multi-echo data array, where `S` is samples, `E` is echos, and `T` is
        time
    tes : (E, ) list
        Echo times
    mask : (S, ) array_like
        Boolean array indicating samples that are consistently (i.e., across
        time AND echoes) non-zero
    masksum : (S, ) array_like
        Valued array indicating number of echos that have sufficient signal in
        given sample
    start_echo : int
        First echo to consider

    Returns
    -------
    t2sa : (S x E x T) :obj:`numpy.ndarray`
        Limited T2* map
    s0va : (S x E x T) :obj:`numpy.ndarray`
        Limited S0 map
    t2ss : (S x E x T) :obj:`numpy.ndarray`
        ???
    s0vs : (S x E x T) :obj:`numpy.ndarray`
        ???
    t2saf : (S x E x T) :obj:`numpy.ndarray`
        Full T2* map
    s0vaf : (S x E x T) :obj:`numpy.ndarray`
        Full S0 map

    Notes
    -----
    1.  Fit monoexponential decay function to all values for a given voxel
        across TRs, per TE, to estimate voxel-wise :math:`S_0` and
        :math:`T_2^*`:
            - :math:`S(TE) = S_0 * exp(-R_2^* * TE)`
            - :math:`T_2^* = 1 / R_2^*`
    2.  Replace infinite values in :math:`T_2^*` map with 500 and NaN values
        in :math:`S_0` map with 0.
    3.  Generate limited :math:`T_2^*` and :math:`S_0` maps by doing something.
    """

    n_samp, n_echos, n_vols = data.shape
    data = data[mask]
    t2ss, s0vs = np.zeros([n_samp, n_echos - 1]), np.zeros([n_samp, n_echos - 1])

    for echo in range(start_echo, n_echos + 1):
        # perform log linear fit of echo times against MR signal
        # make DV matrix: samples x (time series * echos)
        B = np.log((np.abs(data[:, :echo, :]) + 1).reshape(len(data), -1).T)
        # make IV matrix: intercept/TEs x (time series * echos)
        x = np.column_stack([np.ones(echo), [-te for te in tes[:echo]]])
        X = np.repeat(x, n_vols, axis=0)

        beta = np.linalg.lstsq(X, B)[0]
        t2s = 1. / beta[1, :].T
        s0 = np.exp(beta[0, :]).T

        t2s[np.isinf(t2s)] = 500.  # why 500?
        s0[np.isnan(s0)] = 0.      # why 0?

        t2ss[..., echo - 2] = np.squeeze(utils.unmask(t2s, mask))
        s0vs[..., echo - 2] = np.squeeze(utils.unmask(s0, mask))

    # create limited T2* and S0 maps
    fl = np.zeros([n_samp, len(tes) - 1], dtype=bool)
    for echo in range(n_echos - 1):
        fl_ = np.squeeze(fl[..., echo])
        fl_[masksum == echo + 2] = True
        fl[..., echo] = fl_
    t2sa, s0va = utils.unmask(t2ss[fl], masksum > 1), utils.unmask(s0vs[fl], masksum > 1)
    # t2sa[masksum > 1], s0va[masksum > 1] = t2ss[fl], s0vs[fl]

    # create full T2* maps with S0 estimation errors
    t2saf, s0vaf = t2sa.copy(), s0va.copy()
    t2saf[masksum == 1] = t2ss[masksum == 1, 0]
    s0vaf[masksum == 1] = s0vs[masksum == 1, 0]

    return t2sa, s0va, t2ss, s0vs, t2saf, s0vaf


def fit_decay_ts(data, mask, tes, masksum, start_echo):
    """
    Fit voxel- and timepoint-wise monoexponential decay models to estimate
    T2* and S0 timeseries.

    Parameters
    ----------
    data : (S x E x T) array_like
        Multi-echo data array, where `S` is samples, `E` is echos, and `T` is
        time
    tes : (E, ) list
        Echo times
    mask : (S, ) array_like
        Boolean array indicating samples that are consistently (i.e., across
        time AND echoes) non-zero
    masksum : (S, ) array_like
        Valued array indicating number of echos that have sufficient signal in
        given sample
    start_echo : int
        First echo to consider

    Returns
    -------
    t2sa : (S x E x T) :obj:`numpy.ndarray`
        Limited T2* map
    s0va : (S x E x T) :obj:`numpy.ndarray`
        Limited S0 map
    t2ss : (S x E x T) :obj:`numpy.ndarray`
        ???
    s0vs : (S x E x T) :obj:`numpy.ndarray`
        ???
    t2saf : (S x E x T) :obj:`numpy.ndarray`
        Full T2* map
    s0vaf : (S x E x T) :obj:`numpy.ndarray`
        Full S0 map
    """
    nx, ny, nz, n_echos, n_trs = data.shape
    echodata = data[mask]
    tes = np.array(tes)

    t2sa_ts = np.zeros([nx, ny, nz, n_trs])
    s0va_ts = np.zeros([nx, ny, nz, n_trs])
    t2saf_ts = np.zeros([nx, ny, nz, n_trs])
    s0vaf_ts = np.zeros([nx, ny, nz, n_trs])

    for vol in range(echodata.shape[-1]):
        t2ss = np.zeros([nx, ny, nz, n_echos - 1])
        s0vs = t2ss.copy()
        # Fit monoexponential decay first for first echo only,
        # then first two echoes, etc.
        for i_echo in range(start_echo, n_echos + 1):
            B = np.abs(echodata[:, :i_echo, vol]) + 1
            B = np.log(B).transpose()
            neg_tes = -1 * tes[:i_echo]

            # First row is constant, second is TEs for decay curve
            # Independent variables for least-squares model
            x = np.array([np.ones(i_echo), neg_tes])
            X = np.sort(x)[:, ::-1].transpose()

            beta, _, _, _ = np.linalg.lstsq(X, B)
            t2s = 1. / beta[1, :].transpose()
            s0 = np.exp(beta[0, :]).transpose()

            t2s[np.isinf(t2s)] = 500.
            s0[np.isnan(s0)] = 0.

            t2ss[:, :, :, i_echo-2] = np.squeeze(utils.unmask(t2s, mask))
            s0vs[:, :, :, i_echo-2] = np.squeeze(utils.unmask(s0, mask))

        # Limited T2* and S0 maps
        fl = np.zeros([nx, ny, nz, len(tes)-1], bool)
        for i_echo in range(n_echos - 1):
            fl_ = np.squeeze(fl[:, :, :, i_echo])
            fl_[masksum == i_echo + 2] = True
            fl[:, :, :, i_echo] = fl_
        t2sa = np.squeeze(utils.unmask(t2ss[fl], masksum > 1))
        s0va = np.squeeze(utils.unmask(s0vs[fl], masksum > 1))

        # Full T2* maps with S0 estimation errors
        t2saf = t2sa.copy()
        s0vaf = s0va.copy()
        t2saf[masksum == 1] = t2ss[masksum == 1, 0]
        s0vaf[masksum == 1] = s0vs[masksum == 1, 0]

        t2sa_ts[:, :, :, vol] = t2sa
        s0va_ts[:, :, :, vol] = s0va
        t2saf_ts[:, :, :, vol] = t2saf
        s0vaf_ts[:, :, :, vol] = s0vaf

    return t2sa_ts, s0va_ts, t2saf_ts, s0vaf_ts