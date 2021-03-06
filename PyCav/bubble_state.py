import bubble_model as bm
import numpy as np
import scipy.stats as sp
import matplotlib.pyplot as plt
from sys import exit
from moments import get_G

class bubble_state:
    def __init__(self, pop_config={}, model_config={}):

        self.model_config = model_config
        self.pop_config = pop_config
        self.set_defaults()
        self.parse_config()

        # Initiate bubbles, weights, abscissas
        if self.NR0 == 1:
            self.init_mono()
        elif self.NR0 > 1:
            if self.binning == "Simpson":
                self.init_simp()
            elif self.binning == "GL":
                self.init_GL()
            elif self.binning == "GH":
                if self.shape != "lognormal":
                    raise NotImplementedError
                self.init_GH()
            else:
                raise NotImplementedError
        else:
            raise ValueError(self.NR0)

        self.get_bubbles()
        self.periods = 2.*np.pi/np.sqrt(3*1.4/(self.R0**2.))

        # Assume all bubbles have the same model
        self.num_RV_dim = self.bubble[0].num_RV_dim

        self.vals = np.zeros((self.NR0, self.num_RV_dim))
        for i in range(self.NR0):
            self.vals[i, :] = self.bubble[i].state
            # Create view so that bubble state is
            # auto-updated when changing vals
            self.bubble[i].state = self.vals[i, :].view()

        self.rhs = np.zeros((self.NR0, self.num_RV_dim))

    def set_defaults(self):
        self.NR0 = 1
        self.shape = "lognormal"
        self.binning = "Simpson"
        self.sigR0 = 0.3
        self.muR0 = 1.0
        self.moments = [[0, 0]]
        self.Nmom = 1

    def parse_config(self):
        if "NR0" in self.pop_config:
            self.NR0 = self.pop_config["NR0"]

        if "shape" in self.pop_config:
            self.shape = self.pop_config["shape"]

        if "binning" in self.pop_config:
            self.binning = self.pop_config["binning"]

        if "sigR0" in self.pop_config:
            self.sigR0 = self.pop_config["sigR0"]

        if "muR0" in self.pop_config:
            self.muR0 = self.pop_config["muR0"]

        if "moments" in self.pop_config:
            self.moments = self.pop_config["moments"]
            self.Nmom = len(self.moments)

        if "Nfilt" in self.pop_config and "Tfilt" in self.pop_config:
            raise Exception('choose one of Nfilt and Tfilt')
        elif "Nfilt" in self.pop_config:
            self.filter = True
            self.Nfilt = self.pop_config["Nfilt"]
            self.Tfilt = 0 
        elif "Tfilt" in self.pop_config:
            self.filter = True
            self.Tfilt = self.pop_config["Tfilt"]
            self.Nfilt = 0 
        else:
            self.filter = False
            self.Nfilt = 0 
            self.Tfilt = 0 

    def init_pdf(self):
        if self.shape == "lognormal":
            self.f = sp.lognorm.pdf(self.R0, self.sigR0, loc=np.log(self.muR0))
        elif self.shape == "normal":
            self.f = sp.norm.pdf(self.R0, scale=self.sigR0, loc=self.muR0)
        else:
            raise NotImplementedError
        if max(abs(self.f)) < 1.e-6:
            raise Exception('all PDF points are small')

    def init_GH(self):
        """
        Routine for Gauss-Hermite abscissas and weights (Numerical Recipe)
        Roots are symmetric about the origin, then find only half of them
        Translated from Keita Ando Fortran bubbly flow code (c. 2010)
        """

        Npt = self.NR0
        psmall = 3.0e-14
        mxit = 100

        phi_tld = np.zeros(Npt)
        self.w = np.zeros(Npt)

        m = (Npt + 1) // 2

        for i in range(m):
            if i == 0:
                z = np.sqrt(2 * Npt + 1.0) - 1.85575 * (2 * Npt + 1) ** (-0.16667)
            elif i == 1:
                z = z - 1.14 * Npt ** 0.426 / z
            elif i == 2:
                z = 1.86 * z - 0.86 * phi_tld[0]
            elif i == 3:
                z = 1.91 * z - 0.91 * phi_tld[1]
            else:
                z = 2.0 * z - phi_tld[i - 2]

            its = 1
            z1 = 0.0
            while True:
                if its > mxit or abs(z - z1) <= psmall:
                    break
                p1 = np.pi ** (-0.25)
                p2 = 0.0
                for j in range(Npt):
                    p3 = p2
                    p2 = p1
                    p1 = (
                        z * np.sqrt(2.0 / float(j + 1)) * p2
                        - np.sqrt(float(j) / float(j + 1)) * p3
                    )
                pp = np.sqrt(2.0 * Npt) * p2
                z1 = z
                z = z1 - p1 / pp
                its += 1

            phi_tld[i] = z
            phi_tld[Npt - i - 1] = -z
            self.w[i] = 2.0 / (pp ** 2.0)
            self.w[Npt - i - 1] = self.w[i]

        self.w /= np.sqrt(np.pi)
        self.R0 = np.exp(np.sqrt(2.0) * self.sigR0 * phi_tld)

        for i in range(Npt):
            phi_tld[Npt - i - 1] = self.R0[i]
        self.R0 = phi_tld

    def init_GL(self):
        # from here: https://numpy.org/doc/stable/reference/generated/numpy.polynomial.legendre.leggauss.html
        self.get_bounds()

        self.R0, self.w = np.polynomial.legendre.leggauss(self.NR0)
        self.R0 += 1.0
        self.R0 *= 0.5 * (self.b - self.a)
        self.R0 += self.a

        self.init_pdf()
        self.w *= self.f
        self.w /= np.sum(self.w)

    def init_simp(self):
        self.get_bounds()
        self.R0 = np.logspace(
                np.log10(self.a), 
                np.log10(self.b), 
                num=self.NR0)

        self.dR0 = np.zeros(self.NR0)
        for i in range(self.NR0 - 1):
            self.dR0[i] = self.R0[i + 1] - self.R0[i]
        self.dR0[self.NR0 - 1] = self.dR0[self.NR0 - 2]

        self.init_pdf()

        self.w = np.zeros(self.NR0)
        for i in range(self.NR0):
            if i == 0 or i == self.NR0 - 1:
                self.w[i] = 1.0 / 3.0
            elif i % 2 == 0:
                self.w[i] = 2.0 / 3.0
            else:
                self.w[i] = 4.0 / 3.0

        self.w *= self.dR0
        self.w *= self.f
        self.w /= np.sum(self.w)

    def init_mono(self):
        self.w = np.ones(1)
        self.R0 = np.ones(1)*self.muR0

    def get_bounds(self):
        self.a = 0.8 * np.exp(-2.8 * self.sigR0) + (self.muR0 - 1.)
        self.b = 0.2 * np.exp(9.5 * self.sigR0) + 1.0 + (self.muR0 - 1.)
        if (self.a <= 0.):
            raise ValueError(self.a)

    def get_bubbles(self):
        self.bubble = [bm.bubble_model(config=self.model_config, R0=x) for x in self.R0]

    def get_rhs(self, state, p):
        self.vals[:, :] = state
        for i in range(self.NR0):
            self.rhs[i, :] = self.bubble[i].rhs(p)
        return self.rhs

    def get_quad(self, vals=None, filt=False, Nfilt=0, Tfilt=False, shifts=0):
        ret = np.zeros(self.Nmom)
        if filt:
            if Nfilt > 0:
                for k, mom in enumerate(self.moments):
                    if self.num_RV_dim == 2 and len(mom) == 2:
                        G = np.zeros(self.NR0)
                        for q in range(Nfilt):
                            G += vals[q, :, 0] ** mom[0] * vals[q, :, 1] ** mom[1]
                        G /= float(Nfilt)
                        ret[k] = np.sum(self.w[:] * G[:])
                    else:
                        raise Exception('I cant handle a requested moment...')
            elif Tfilt:
                for k, mom in enumerate(self.moments):
                    if self.num_RV_dim == 2 and len(mom) == 2:
                        # vals[ time, R0_node, int_coordinate ]
                        # Get max number of times (going backward)
                        Nt = len(vals[:,0,0])
                        # G = np.zeros(self.NR0)
                        G = get_G(vals=vals,
                                mom=np.array(mom),
                                Nt=Nt,
                                shifts=shifts,
                                NR0=self.NR0)
                        # for i in range(self.NR0):
                        #     G[i] = 0.
                        #     for q in range(Nt-1,Nt-1+shifts[i],-1):
                        #         G[i] += (
                        #                 vals[q, i, 0] ** mom[0] * 
                        #                 vals[q, i, 1] ** mom[1]
                        #             )
                        #     G[i] /= (abs(shifts[i]) + 1.)

                        ret[k] = np.sum(self.w[:] * G[:])
                    else:
                        raise Exception('I cant handle a requested moment...')
            else:
                raise Exception('Need one of Nfilt or Tfilt')
        else:
            for k, mom in enumerate(self.moments):
                if self.num_RV_dim == 2 and len(mom) == 2:
                    ret[k] = np.sum(
                        self.w[:] * vals[:, 0] ** mom[0] * vals[:, 1] ** mom[1]
                    )
                elif self.num_RV_dim == 2 and len(mom) == 3:
                    ret[k] = np.sum(
                        self.w[:]
                        * vals[:, 0] ** mom[0]
                        * vals[:, 1] ** mom[1]
                        * self.R0[:] ** mom[2]
                    )
                else:
                    raise Exception

        return ret
