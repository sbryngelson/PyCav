import bubble_state as bs
import waveforms as wf
import numpy as np
from sys import exit
import matplotlib.pyplot as plt


class time_advancer:
    def __init__(self, config={}):

        self.config = config
        self.parse_config()

        self.max_time_step = 1.0e5
        self.min_time_step = self.dt

        self.set_stepper()

    def set_stepper(self):
        if self.method == "Euler":
            self.advance = self.euler
            self.n_stages = 0
        elif self.method == "RK2":
            self.advance = self.rk2
            self.n_stages = 1
        elif self.method == "RK3":
            self.advance = self.rk3
            self.n_stages = 1
        elif self.method == "RK12":
            self.advance = self.rk12
            self.n_stages = 1
        elif self.method == "RK23":
            self.advance = self.rk23
            self.n_stages = 1
        else:
            raise NotImplementedError

    def parse_config(self):
        if "T" in self.config:
            self.T = self.config["T"]
            if self.T <= 0:
                raise ValueError(self.T)
        else:
            raise Exception("No final time T")

        if "dt" in self.config:
            self.dt = self.config["dt"]
            if self.dt <= 0.0:
                raise ValueError(self.dt)
        else:
            raise Exception("No time step dt")

        if "method" in self.config:
            self.method = self.config["method"]
        else:
            self.method = "Euler"

        if "error_tol" in self.config:
            self.error_tol = self.config["error_tol"]
            if self.error_tol <= 0.0:
                raise ValueError(self.error_tol)
        elif self.method == "RK23" or self.method == "RK12":
            raise Exception("Need error tolerance")
        else:
            self.error_tol = 0.0

        if "Nfilt" in self.config:
            self.filter = True
            self.Nfilt = self.config["Nfilt"]
        else:
            self.filter = False
            self.Nfilt = 0

    def initialize_state(self, pop_config=None, model_config=None):
        self.state = bs.bubble_state(pop_config=pop_config, model_config=model_config)

    def initialize_wave(self, wave_config=None):
        self.wave = wf.waveforms(config=wave_config)

    def euler(self):
        f0 = self.state.vals.copy()
        p = self.wave.p(self.time)
        l1 = self.state.get_rhs(f0, p)
        self.state.vals[:, :] = f0 + self.dt * l1

    def rk2(self):
        f0 = self.state.vals.copy()

        p = self.wave.p(self.time)
        l1 = self.state.get_rhs(f0, p)
        f1 = f0 + self.dt * l1

        pdt = self.wave.p(self.time + self.dt)
        L = self.state.get_rhs(f1, pdt)

        self.state.vals[:, :] = 0.5 * f0 + 0.5 * (f1 + self.dt * L)

    def rk3(self):
        f0 = self.state.vals.copy()

        p = self.wave.p(self.time)
        l1 = self.state.get_rhs(f0, p)
        f1 = f0 + self.dt * l1

        pdt = self.wave.p(self.time + self.dt)
        L = self.state.get_rhs(f1, pdt)
        f2 = 0.75 * f0 + 0.25 * (f1 + self.dt * L)

        pdt2 = self.wave.p(self.time + self.dt / 2.0)
        L2 = self.state.get_rhs(f2, pdt2)

        self.state.vals[:, :] = 1.0 / 3.0 * f0 + 2.0 / 3.0 * (f2 + self.dt * L2)

    def rk12(self):
        f0 = self.state.vals.copy()

        p = self.wave.p(self.time)
        l1 = self.state.get_rhs(f0, p)
        f1 = f0 + self.dt * l1
        mome = f1.copy()

        pdt = self.wave.p(self.time + self.dt)
        L = self.state.get_rhs(f1, pdt)

        mom = 0.5 * f0 + 0.5 * (f1 + self.dt * L)

        self.state.vals[:, :] = mom
        self.ts_error = self.err(fine=mom, coarse=mome)

    def rk23(self):
        # SSP-RK2
        f0 = self.state.vals.copy()

        p = self.wave.p(self.time)
        l1 = self.state.get_rhs(f0, p)
        f1 = f0 + self.dt * l1

        pdt = self.wave.p(self.time + self.dt)
        L = self.state.get_rhs(f1, pdt)

        mome = 0.5 * f0 + 0.5 * (f1 + self.dt * L)

        # SSP-RK3
        f2 = 0.75 * f0 + 0.25 * (f1 + self.dt * L)
        pdt2 = self.wave.p(self.time + self.dt / 2.0)
        L2 = self.state.get_rhs(f2, pdt2)
        mom = 1.0 / 3.0 * f0 + 2.0 / 3.0 * (f2 + self.dt * L2)
        self.state.vals[:, :] = mom
        self.ts_error = self.err(fine=mom, coarse=mome)

    def err(self, fine=0.0, coarse=0.0):
        return np.linalg.norm(fine - coarse) / np.linalg.norm(fine)

    def adapt_stepsize(self):
        error_fraction = np.sqrt(0.5 * self.error_tol / self.ts_error)
        time_step_factor = min(max(error_fraction, 0.3), 2.0)
        new_time_step = time_step_factor * self.dt
        new_time_step = min(
            max(0.9 * new_time_step, self.min_time_step), self.max_time_step
        )
        self.dt = new_time_step

    def run(self):
        self.time = 0.0
        i_step = 0
        step = True
        self.save = []
        self.times = []
        # np.set_printoptions(precision=24)

        # plt.ion()

        while step:
            print(
                "Step: ",
                i_step,
                "TS Ratio:",
                round(self.dt / self.min_time_step, 2),
                "Percent completed:",
                round(100 * self.time / self.T, 1),
            )
            self.times.append(self.time)
            self.save.append(self.state.vals.copy())
            self.advance()
            i_step += 1
            self.time += self.dt

            # if i_step % 100 == 0:
            # plt.plot(self.state.R0, self.state.vals[:,0])
            # plt.plot(self.state.R0, self.state.vals[:,1])
            # plt.xscale('log')
            # plt.draw()
            # plt.pause(1e-5)
            # plt.clf()

            if self.method == "RK23" or self.method == "RK12":
                self.adapt_stepsize()

            if self.time >= self.T:
                step = False

        self.save = np.array(self.save, dtype=np.float32)
