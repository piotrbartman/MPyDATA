"""
Created at 25.09.2019

@author: Piotr Bartman
@author: Michael Olesik
@author: Sylwester Arabas
"""

from .arakawa_c.scalar_field import ScalarField
from .arakawa_c.vector_field import VectorField
from .arakawa_c.traversal import Traversal
from .formulae import fct_utils as fct
from .options import Options
from .arrays import Arrays
import numpy as np


class MPDATA:
    def __init__(self,
        opts: Options,
        state: ScalarField,
        g_factor: ScalarField,
        GC_field: VectorField,
    ):
        self.arrays = Arrays(state, g_factor, GC_field, opts)
        self.opts = opts

    def clone(self):
        return MPDATA(
            self.opts.clone(),
            self.arrays.curr.clone(),
            self.arrays.G.clone(),
            self.arrays.GC_phys.clone(),
        )

    def step(self, n_iters, mu=0., debug=False):
        assert n_iters > 0
        assert mu == 0 or self.opts.nzm

        self.fct_init(psi=self.arrays.curr, n_iters=n_iters)
        if self.opts.nzm:
            assert self.arrays.curr.dimension == 1  # TODO
            assert self.opts.nug is False

            self.arrays.GC_curr.apply(self.opts.formulae["laplacian"], args=(self.arrays.curr, mu))
            self.arrays.GC_curr.add(self.arrays.GC_phys)
        else:
            self.arrays.GC_curr.swap_memory(self.arrays.GC_phys)

        for i in range(n_iters):
            self.arrays.prev.swap_memory(self.arrays.curr)
            self.arrays.GC_prev.swap_memory(self.arrays.GC_curr)

            if i > 0:
                self.arrays.GC_curr.apply(
                    self.opts.formulae["antidiff"],
                    args=(self.arrays.prev, self.arrays.GC_prev, self.arrays.G)
                )
                self.fct_adjust_antidiff(self.arrays.GC_curr, i, flux=self.arrays.GC_prev, n_iters=n_iters)
            else:
                self.arrays.GC_curr.swap_memory(self.arrays.GC_prev)

            self.upwind(i, flux=self.arrays.GC_prev,
                        check_conservativeness=debug,
                        check_CFL=debug
                        )

            if i == 0 and not self.opts.nzm:
                self.arrays.GC_phys.swap_memory(self.arrays.GC_curr)

    def upwind(self, i: int, flux: VectorField, check_conservativeness, check_CFL):
        if check_CFL:
            # TODO: 2D, 3D, ...
            assert (np.abs(self.arrays.GC_curr.get_component(0)) <= 1).all()

        flux.apply(
            traversal=self.opts.formulae["flux"][0 if i == 0 else 1],
            args=(self.arrays.prev, self.arrays.GC_curr)
        )
        self.arrays.curr.apply(
            traversal=self.opts.formulae["upwind"],
            args=(flux, self.arrays.G),
        )
        self.arrays.curr.add(self.arrays.prev)

        if check_conservativeness:
            # TODO: 2D, 3D, ...
            sum_0 = np.sum(self.arrays.prev.get() * self.arrays.G.get())
            sum_1 = np.sum(self.arrays.curr.get() * self.arrays.G.get())
            bcflux = flux._impl.get_item(0, -.5) - flux._impl.get_item(-1, +.5)
            np.testing.assert_approx_equal(sum_0, sum_1 + bcflux, significant=13)

    def fct_init(self, psi: ScalarField, n_iters: int):
        if n_iters == 1 or not self.opts.fct:
            return

        tmp = self.arrays.psi_min
        tmp.apply(traversal=Traversal(body=fct.psi_min_1, init=np.inf, loop=True), args=(psi,), ext=1)
        self.arrays.psi_min.apply(traversal=Traversal(body=fct.psi_min_2, init=np.nan, loop=False), args=(psi, tmp), ext=1)

        tmp = self.arrays.psi_max
        tmp.apply(traversal=Traversal(body=fct.psi_max_1, init=-np.inf, loop=True), args=(psi,), ext=1)
        self.arrays.psi_max.apply(traversal=Traversal(body=fct.psi_max_2, init=np.nan, loop=False), args=(psi, tmp), ext=1)

    def fct_adjust_antidiff(self, GC: VectorField, it: int, flux: VectorField, n_iters: int):
        if n_iters == 1 or not self.opts.fct:
            return
        flux.apply(traversal=self.opts.formulae["flux"][0 if it == 0 else 1], args=(self.arrays.prev, GC), ext=1)

        beta_up_nom = self.arrays.beta_up
        beta_up_den = self.arrays.tmp
        beta_up_nom.apply(traversal=Traversal(body=fct.beta_up_nom_1, init=-np.inf, loop=True), args=(self.arrays.prev,), ext=1)
        beta_up_nom.apply(traversal=Traversal(body=fct.beta_up_nom_2, init=np.nan, loop=False), args=(self.arrays.prev, self.arrays.psi_max, self.arrays.beta_up, self.arrays.G), ext=1)
        beta_up_den.apply(traversal=Traversal(body=fct.beta_up_den, init=0, loop=True), args=(flux,), ext=1)
        self.arrays.beta_up.apply(traversal=Traversal(body=fct.frac, init=np.nan, loop=False), args=(beta_up_nom, beta_up_den), ext=1)

        beta_dn_nom = self.arrays.beta_dn
        beta_dn_den = self.arrays.tmp
        beta_dn_nom.apply(traversal=Traversal(body=fct.beta_dn_nom_1, init=np.inf, loop=True), args=(self.arrays.prev,), ext=1)
        beta_dn_nom.apply(traversal=Traversal(body=fct.beta_dn_nom_2, init=np.nan, loop=False), args=(self.arrays.prev, self.arrays.psi_min, self.arrays.beta_dn, self.arrays.G), ext=1)
        beta_dn_den.apply(traversal=Traversal(body=fct.beta_dn_den, init=0, loop=True), args=(flux,), ext=1)
        self.arrays.beta_dn.apply(traversal=Traversal(body=fct.frac, init=np.nan, loop=False), args=(beta_dn_nom, beta_dn_den), ext=1)

        GC.apply(traversal=self.opts.formulae["GC_mono"], args=(GC, self.arrays.beta_up, self.arrays.beta_dn))
