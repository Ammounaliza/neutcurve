"""
==================
hillcurve
==================

Defines :class:`HillCurve` for fitting neutralization curves.
"""

import collections
import math

import matplotlib.pyplot as plt

import pandas as pd

import scipy
import scipy.optimize


class HillCurve:
    r"""A fitted Hill curve, optionally with free baselines.

    Fits :math:`f\left(c\right) = b + \frac{t - b}{1 + \left(c/m\right)^s}`
    where :math:`f\left(c\right)` is the fraction infectivity remaining
    at concentration :math:`c`, :math:`m` is the midpoint
    of the neutralization curve, :math:`t` is the top
    value (e.g., 1), :math:`b` is the bottom value (e.g., 0),
    and :math:`s` is the slope of the curve. Because
    :math:`f\left(c\right)` is the fraction infectivity remaining, we expect
    :math:`f\left(c\right)` to get smaller as :math:`c` gets larger.
    This should lead us to fit :math:`s > 0`.

    When :math:`t = 1` and :math:`b = 0`, this equation is identical to the
    `Hill curve <https://en.wikipedia.org/wiki/Hill_equation_(biochemistry)>`_,
    except that we are calcuating the fraction **unbound** rather than
    the fraction bound.

    Args:
        `cs` (array-like)
            Concentrations of antibody / serum.
        `fs` (array-like)
            Fraction infectivity remaining at each concentration.
        `fs_stderr` (`None` or array-like)
            If not `None`, standard errors on `fs`.
        `fixbottom` (bool or a float)
            If `True`, fix bottom of curve to to this value; otherwise fit.
        `fixtop` (`False` or a float)
            If `True`, fix top of curve to this value; otherwise fit.
        `fitlogc` (bool)
            Do we do the actual fitting on the concentrations or log
            concentrations? Gives equivalent results in principle, but
            fitting to log concentrations may be more efficient in pratice.

    Attributes:
        `cs` (numpy array)
            Concentrations, sorted from low to high.
        `fs` (numpy array)
            Fraction infectivity, ordered to match sorted concentrations.
        `fs_stderr` (numpy array or `None`)
            Standard errors on `fs`.
        `bottom` (float)
            Bottom of curve, :math:`b` in equation above.
        `top` (float)
            Top of curve, :math:`t` in equation above.
        `midpoint` (float)
            Midpoint of curve, :math:`m` in equation above. Note
            that the midpoint may **not** be the same as the :meth:`ic50`
            if :math:`t \ne 1` or :math:`b \ne 0`.
        `slope` (float)
            Hill slope of curve, :math:`s` in equation above.

    Use the :meth:`ic50` method to get the fitted IC50.

    Here are some examples. First, we import the necessary modules:

    .. nbplot::

        >>> import scipy
        >>>
        >>> from neutcurve import HillCurve
        >>> from neutcurve.colorschemes import CBPALETTE

    Now simulate some data:

    .. nbplot::

        >>> m = 0.03
        >>> s = 1.9
        >>> b = 0.1
        >>> t = 1.0
        >>> cs = [0.002 * 2**x for x in range(9)]
        >>> fs = [HillCurve.evaluate(c, m, s, b, t) for c in cs]

    Now fit to these data, and confirm that the fitted values
    are close to the ones used for the simulation:

    .. nbplot::

        >>> neut = HillCurve(cs, fs)
        >>> scipy.allclose(neut.midpoint, m)
        True
        >>> scipy.allclose(neut.slope, s)
        True
        >>> scipy.allclose(neut.top, t)
        True
        >>> scipy.allclose(neut.bottom, b)
        True

    Since we fit the curve to simulated data where the bottom was
    0.1 rather than 0, the midpoint and IC50 are different. Specifically,
    the IC50 is larger than the midpoint as you have to go past the midpoint
    to get down to 0.5 fraction infectivity:

    .. nbplot::

        >>> neut.ic50() > neut.midpoint
        True
        >>> scipy.allclose(neut.ic50(), 0.0337385586)
        True
        >>> scipy.allclose(0.5, neut.fracinfectivity(neut.ic50()))
        True
        >>> neut.fracinfectivity(neut.midpoint) > 0.5
        True

    Now here is an example where we constrain both the top
    and the bottom (to 1 and 0, respectively) and fit
    the curve. Now the midpoint and IC50 are the same:

    .. nbplot::

        >>> b2 = 0
        >>> t2 = 1
        >>> fs2 = [HillCurve.evaluate(c, m, s, b2, t2) for c in cs]
        >>> neut2 = HillCurve(cs, fs2, fixbottom=b2)
        >>> scipy.allclose(neut2.midpoint, m)
        True
        >>> scipy.allclose(neut2.ic50(), m)
        True

    Now let's fit to concentrations that are all **less**
    than the midpoint, so that we never get to complete neutralization.
    The estimated IC50 is unreliable, and so will be returned as `None` unless
    we call :meth:`ic50` with `method` set to 'bound':

    .. nbplot::

        >>> cs3 = [1e-5 * 2**x for x in range(7)]
        >>> (cs3[-1] < m)
        True
        >>> fs3 = [HillCurve.evaluate(c, m, s, b2, t2) for c in cs3]
        >>> neut3 = HillCurve(cs3, fs3, fixbottom=b2)
        >>> neut3.ic50() is None
        True
        >>> scipy.allclose(neut3.ic50(method='bound'), cs3[-1])
        True

    Note that we can determine if the IC50 is interpolated or an upper
    or lower bound using :meth:`ic50_bound`, and get a nice string
    using :meth:`ic50_str`:

    .. nbplot::

        >>> neut.ic50_bound()
        'interpolated'
        >>> neut3.ic50_bound()
        'upper'
        >>> neut.ic50_str()
        '0.0337'
        >>> neut3.ic50_str()
        '>0.00064'

    We can use the :meth:`dataframe` method to get the measured
    data and fit data at selected points. First, we do this
    just at measured points:

    .. nbplot::

        >>> neut.dataframe('measured').round(3)
           concentration  measurement    fit  stderr
        0          0.002        0.995  0.995     NaN
        1          0.004        0.981  0.981     NaN
        2          0.008        0.932  0.932     NaN
        3          0.016        0.791  0.791     NaN
        4          0.032        0.522  0.522     NaN
        5          0.064        0.272  0.272     NaN
        6          0.128        0.154  0.154     NaN
        7          0.256        0.115  0.115     NaN
        8          0.512        0.104  0.104     NaN

    Then we add in one more point:

    .. nbplot::

        >>> neut.dataframe([0.6]).round(3)
           concentration  measurement    fit  stderr
        0          0.002        0.995  0.995     NaN
        1          0.004        0.981  0.981     NaN
        2          0.008        0.932  0.932     NaN
        3          0.016        0.791  0.791     NaN
        4          0.032        0.522  0.522     NaN
        5          0.064        0.272  0.272     NaN
        6          0.128        0.154  0.154     NaN
        7          0.256        0.115  0.115     NaN
        8          0.512        0.104  0.104     NaN
        9          0.600          NaN  0.103     NaN

    In reality, you'd typically just call :meth:`dataframe` with
    the default argument of 'auto' to get a good range to plot.
    This is done if we call the :meth:`HillCurve.plot` method:

    .. nbplot::

        >>> fig, ax = neut.plot()

    Finally, we confirm that we get the same result regardless
    of whether we fit using the concentrations in linear or
    log space:

    .. nbplot::

        >>> neut_linear = HillCurve(cs, fs, fitlogc=False)
        >>> all(scipy.allclose(getattr(neut, attr), getattr(neut_linear, attr))
        ...     for attr in ['top', 'bottom', 'slope', 'midpoint'])
        True

    """

    def __init__(self,
                 cs,
                 fs,
                 *,
                 fs_stderr=None,
                 fixbottom=False,
                 fixtop=1,
                 fitlogc=True,
                 ):
        """See main class docstring."""
        # get data into arrays sorted by concentration
        self.cs = scipy.array(cs)
        self.fs = scipy.array(fs)
        if fs_stderr is not None:
            self.fs_stderr = scipy.array(fs_stderr)
            self.fs_stderr = self.fs_stderr[self.cs.argsort()]
        else:
            self.fs_stderr = None
        self.fs = self.fs[self.cs.argsort()]
        self.cs = self.cs[self.cs.argsort()]

        if any(self.cs <= 0):
            raise ValueError('concentrations in `cs` must all be > 0')

        # make initial guess for slope to have the right sign
        if self.fs[0] >= self.fs[-1]:
            self.slope = 1.5
        else:
            self.slope = -1.5

        # make initial guess for top and bottom
        if fixtop is False:
            if self.slope > 0:
                self.top = self.fs.max()
            else:
                self.top = self.fs.min()
        else:
            if not isinstance(fixtop, (int, float)):
                raise ValueError('`fixtop` is not `False` or a number')
            self.top = fixtop
        if fixbottom is False:
            if self.slope > 0:
                self.bottom = self.fs.min()
            else:
                self.bottom = self.fs.max()
        else:
            if not isinstance(fixbottom, (int, float)):
                raise ValueError('`fixbottom` is not `False` or a number')
            self.bottom = fixbottom

        # make initial guess for midpoint
        midval = (self.top - self.bottom) / 2.0
        if (self.fs > midval).all():
            if self.slope > 0:
                self.midpoint = self.cs[-1]
            else:
                self.midpoint = self.cs[0]
        elif (self.fs <= midval).all():
            if self.slope > 0:
                self.midpoint = self.cs[0]
            else:
                self.midpoint = self.cs[-1]
        else:
            # get first index where f crosses midpoint
            i = scipy.argmax((self.fs > midval)[:-1] !=
                             (self.fs > midval)[1:])
            assert (self.fs[i] > midval) != (self.fs[i + 1] > midval)
            self.midpoint = (self.cs[i] + self.cs[i + 1]) / 2.0

        # set up function and initial guesses
        if fitlogc:
            evalfunc = self.evaluate_log
            xdata = scipy.log(self.cs)
        else:
            evalfunc = self.evaluate
            xdata = self.cs
        if fixtop is False and fixbottom is False:
            func_vars = ['midpoint', 'slope', 'bottom', 'top']
            func = evalfunc
        elif fixtop is False:
            func_vars = ['midpoint', 'slope', 'top']

            def func(c, m, s, t):
                return evalfunc(c, m, s, self.bottom, t)

        elif fixbottom is False:
            func_vars = ['midpoint', 'slope', 'bottom']

            def func(c, m, s, b):
                return evalfunc(c, m, s, b, self.top)
        else:
            func_vars = ['midpoint', 'slope']

            def func(c, m, s):
                return evalfunc(c, m, s, self.bottom, self.top)

        initguess = [getattr(self, varname) for varname in func_vars]

        (popt, pcov) = scipy.optimize.curve_fit(
                f=func,
                xdata=xdata,
                ydata=self.fs,
                p0=initguess,
                sigma=self.fs_stderr,
                )

        for i, varname in enumerate(func_vars):
            setattr(self, varname, popt[i])

    def ic50(self, method='interpolate'):
        r"""IC50 value.

        Concentration where infectivity remaining is 0.5. Equals
        `midpoint` if and only if `top = 1` and `bottom = 0`. Calculated
        from :math:`0.5 = b + \frac{t - b}{1 + (ic50/m)^s}`, which solves to
        :math:`ic50 = m \times \left(\frac{t - 0.5}{0.5 - b}\right)^{1/s}`

        Args:
            `method` (str)
                Can have following values:

                  - 'interpolate': only return a number for IC50 if it
                    is in range of concentrations, otherwise return `None`.

                  - 'bound': if IC50 is out of range of concentrations,
                    return upper or lower measured concentration depending
                    on if IC50 is above or below range of concentrations.
                    Assumes infectivity decreases with concentration.

        Returns:
            Number giving IC50 or `None` (depending on value of `method`).

        """
        if self.top < 0.5 and self.bottom < 0.5:
            bound = 'bottom'
        elif self.top >= 0.5 and self.bottom >= 0.5:
            bound = 'upper'
        else:
            ic50 = (self.midpoint * ((self.top - 0.5) /
                    (0.5 - self.bottom))**(1.0 / self.slope))
            if (self.cs[0] <= ic50 <= self.cs[-1]):
                return ic50
            elif ic50 < self.cs[0]:
                bound = 'bottom'
            else:
                bound = 'upper'

        if method == 'bound':
            if bound == 'upper':
                return self.cs[-1]
            elif bound == 'lower':
                return self.cs[0]
            else:
                raise ValueError(f"invalid `bound` {bound}")
        elif method != 'interpolate':
            raise ValueError(f"invalid `method` of {method}")

    def ic50_bound(self):
        """Is IC50 'interpolated', or an 'upper' or 'lower' bound."""
        if self.ic50(method='interpolate') is not None:
            return 'interpolated'
        else:
            ic50 = self.ic50(method='bound')
            if ic50 == self.cs[0]:
                return 'lower'
            elif ic50 == self.cs[-1]:
                return 'upper'
            else:
                raise RuntimeError('ic50 is not upper or lower bound')

    def ic50_str(self, precision=3):
        """IC50 as string indicating upper / lower bounds with > or <.

        Args:
            Number of significant digits in returned string.

        """
        ic50 = f"{{:.{precision}g}}".format(self.ic50('bound'))
        prefix = {'interpolated': '',
                  'lower': '<',
                  'upper': '>'}[self.ic50_bound()]
        return f"{prefix}{ic50}"

    def fracinfectivity(self, c):
        """Fraction infectivity at `c` for fitted parameters."""
        return self.evaluate(c, self.midpoint, self.slope,
                             self.bottom, self.top)

    @staticmethod
    def evaluate(c, m, s, b, t):
        r""":math:`f\left(c\right) = b + \frac{t-b}{1+\left(c/m\right)^s}`."""
        return b + (t - b) / (1 + (c / m)**s)

    @staticmethod
    def evaluate_log(logc, m, s, b, t):
        """Like :class:`HillCurve.evaluate` but takes natural log :math:`c`."""
        return b + (t - b) / (1 + (scipy.exp(logc) / m)**s)

    def plot(self,
             *,
             concentrations='auto',
             ax=None,
             xlabel='concentration',
             ylabel='fraction infectivity',
             color='black',
             marker='o',
             markersize=6,
             linewidth=1,
             linestyle='-',
             ):
        """Plot the neutralization curve.

        Args:
            `concentrations`
                Concentrations to plot, same meaning as for
                :meth:`HillCurve.dataframe`.
            `ax` (`None` or matplotlib axes.Axes object)
                Use to plot on an existing axis. If using an existing
                axis, do **not** re-scale the axis limits to the data.
            `xlabel` (str or `None`)
                Label for x-axis.
            `ylabel` (str or `None`)
                Label for y-axis.
            `color` (str)
                Color of line and point.
            `marker` (str)
                Marker shape: https://matplotlib.org/api/markers_api.html
            `markersize` (float)
                Size of point marker.
            `linewidth` (float)
                Width of line.
            `linestyle` (str)
                Line style.

        Returns:
            The 2-tuple `(fig, ax)` giving the matplotlib figure and axis.

        """
        data = self.dataframe(concentrations)

        if ax is None:
            fig, ax = plt.subplots()
            fig.set_size_inches((4, 3))
            check_ybounds = True
            ylowerbound = -0.05
            yupperbound = 1.05
            ax.autoscale(True, 'both')
        else:
            fig = ax.get_figure()
            ax.autoscale(False, 'both')
            check_ybounds = False

        ax.plot('concentration',
                'fit',
                data=data,
                linestyle=linestyle,
                linewidth=linewidth,
                color=color,
                )

        ax.errorbar(x='concentration',
                    y='measurement',
                    yerr='stderr',
                    data=data,
                    fmt=marker,
                    color=color,
                    markersize=markersize,
                    capsize=markersize / 1.5,
                    )

        ax.set_xscale('log')
        ax.set_xlabel(xlabel, fontsize=15)
        ax.set_ylabel(ylabel, fontsize=15)
        ax.tick_params('both', labelsize=12)

        if check_ybounds:
            ymin, ymax = ax.get_ylim()
            ax.set_ylim(min(ymin, ylowerbound), max(ymax, yupperbound))

        return fig, ax

    def dataframe(self, concentrations='auto'):
        """Get data frame with curve data for plotting.

        Useful if you want to get both the points and the fit
        curve to plot.

        Args:
            `concentrations` (array-like or 'auto' or 'measured')
                Concentrations for which we compute the fit values.
                If 'auto' the automatically computed from data
                range using :func:`concentrationRange`. If
                'measured' then only include measured values.

        Returns:
            A pandas DataFrame with the following columns:

              - 'concentration': concentration
              - 'fit': curve fit value at this point
              - 'measurement': value of measurement at this point,
                or numpy.nan if no measurement here.
              - 'stderr': standard error of measurement if provided.

        """
        if concentrations == 'auto':
            concentrations = concentrationRange(self.cs[0], self.cs[-1])
        elif concentrations == 'measured':
            concentrations = []
        concentrations = scipy.concatenate([self.cs, concentrations])
        n = len(concentrations)

        points = scipy.concatenate([self.fs,
                                    scipy.full(n - len(self.fs), scipy.nan)
                                    ])

        if self.fs_stderr is None:
            stderr = scipy.full(n, scipy.nan)
        else:
            stderr = scipy.concatenate([self.fs_stderr,
                                        scipy.full(n - len(self.fs), scipy.nan)
                                        ])

        fit = scipy.array([self.fracinfectivity(c) for c in concentrations])

        return (pd.DataFrame.from_dict(
                    collections.OrderedDict(
                        [('concentration', concentrations),
                         ('measurement', points),
                         ('fit', fit),
                         ('stderr', stderr),
                         ])
                    )
                .sort_values('concentration')
                .reset_index(drop=True)
                )


def concentrationRange(bottom, top, npoints=200, extend=0.1):
    """Logarithmically spaced concentrations for plotting.

    Useful if you want to plot a curve by fitting values to densely
    sampled points and need the concentrations at which to compute
    these points.

    Args:
        `bottom` (float)
            Lowest concentration.
        `top` (float)
            Highest concentration.
        `npoints` (int)
            Number of points.
        `extend` (float)
            After transforming to log space, extend range of points
            by this much below and above `bottom` and `top`.

    Returns:
        A numpy array of `npoints` concentrations.

    >>> scipy.allclose(concentrationRange(0.1, 100, 10, extend=0),
    ...                [0.1, 0.22, 0.46, 1, 2.15, 4.64, 10, 21.54, 46.42, 100],
    ...                atol=1e-2)
    True
    >>> scipy.allclose(concentrationRange(0.1, 100, 10),
    ...                [0.05, 0.13, 0.32, 0.79, 2.00, 5.01,
    ...                 12.59, 31.62, 79.43, 199.53],
    ...                atol=1e-2)
    True

    """
    if top <= bottom:
        raise ValueError('`bottom` must be less than `top`')
    if bottom <= 0:
        raise ValueError('`bottom` must be greater than zero')
    if extend < 0:
        raise ValueError('`extend` must be >= 0')

    logbottom = math.log10(bottom)
    logtop = math.log10(top)
    logrange = logtop - logbottom
    assert logrange > 0
    bottom = logbottom - logrange * extend
    top = logtop + logrange * extend

    return scipy.logspace(bottom, top, npoints)


if __name__ == '__main__':
    import doctest
    doctest.testmod()
