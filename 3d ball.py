"""A sphere of density 500 falling into a hydrostatic tank (15 minutes)
Check basic equations of SPH to throw a ball inside the vessel
"""
from __future__ import print_function
import numpy as np

# PySPH base and carray imports
from pysph.base.utils import (get_particle_array_wcsph,
                              get_particle_array_rigid_body)
from pysph.base.kernels import CubicSpline

from pysph.solver.solver import Solver
from pysph.sph.integrator import EPECIntegrator
from pysph.sph.integrator_step import WCSPHStep

from pysph.sph.equation import Group
from pysph.sph.basic_equations import (XSPHCorrection, ContinuityEquation,
                                       SummationDensity)
from pysph.sph.wc.basic import TaitEOSHGCorrection, MomentumEquation
from pysph.solver.application import Application
from pysph.sph.rigid_body import (BodyForce, RigidBodyCollision, LiuFluidForce,
                                  RigidBodyMoments, RigidBodyMotion,
                                  RK2StepRigidBody)


def create_boundary():
    dx = 2

    # bottom particles in tank
    xb = np.arange(-2 * dx, 100 + 2 * dx, dx)
    yb = np.arange(-10, 0, dx)
    zb = np.arange(-4, 4, dx)
    xb, yb, zb = np.meshgrid(xb, yb, zb)
    xb = xb.ravel()
    yb = yb.ravel()
    zb = zb.ravel()

    x = np.concatenate([xb])
    y = np.concatenate([yb])
    z = np.concatenate([zb])

    return x * 1e-3, y * 1e-3, z * 1e-3


def create_fluid():
    dx = 2
    xf = np.arange(0, 100, dx)
    yf = np.arange(0, 30, dx)
    zf = np.arange(-7, 7, dx)
    xf, yf, zf = np.meshgrid(xf, yf, zf)
    xf = xf.ravel()
    yf = yf.ravel()
    zf = zf.ravel()

    return xf * 1e-3, yf * 1e-3, zf * 1e-3


def create_sphere(dx=0.5):
    x = np.arange(-100, 100, dx)
    y = np.arange(0, 150, dx)
    z = np.arange(-4, 40, dx)
    x, y, z = np.meshgrid(x, y, z)
    x = x.ravel()
    y = y.ravel()
    z = z.ravel()

    p = ((x - 50)**2 + (y - 15)**2 + (z - 20)**2) < 2**2
    x = x[p]
    y = y[p]
    z = z[p]

    # lower sphere a little
    return x * 1e-3, y * 1e-3, z * 1e-3


def get_density(y):
    height = 150
    c_0 = 2 * np.sqrt(2 * 9.81 * height * 1e-3)
    rho_0 = 1000
    height_water_clmn = height * 1e-3
    gamma = 7.
    _tmp = gamma / (rho_0 * c_0**2)

    rho = np.zeros_like(y)
    for i in range(len(rho)):
        p_i = rho_0 * 9.81 * (height_water_clmn - y[i])
        rho[i] = rho_0 * (1 + p_i * _tmp)**(1. / gamma)
    return rho


def geometry():
    # please run this function to know how
    # geometry looks like
    import matplotlib.pyplot as plt
    x_tank, y_tank, z_tank = create_boundary()
    x_fluid, y_fluid, z_fluid = create_fluid()
    x_cube, y_cube, z_cube = create_sphere()
    plt.scatter(x_fluid, y_fluid, z_fluid)
    plt.scatter(x_tank, y_tank, z_tank)
    plt.scatter(x_cube, y_cube, z_cube)
    plt.axes().set_aspect('equal', 'datalim')
    print("done")
    plt.show()


class RigidFluidCoupling(Application):
    def initialize(self):
        self.dx = 2 * 1e-3
        self.hdx = 1.2
        self.ro = 1000
        self.solid_rho = 500
        self.vz = -2.0
        self.m = 1000 * self.dx * self.dx
        self.co = 2 * np.sqrt(2 * 9.81 * 150 * 1e-3)
        self.alpha = 0.1

    def create_particles(self):
        """Create the circular patch of fluid."""
        xf, yf, zf = create_fluid()
        rho = get_density(yf)
        m = rho[:] * self.dx * self.dx * self.dx
        rho = np.ones_like(xf) * self.ro
        h = np.ones_like(xf) * self.hdx * self.dx
        fluid = get_particle_array_wcsph(x=xf, y=yf, z=zf, h=h, m=m, rho=rho,
                                         name="fluid")

        xt, yt, zt = create_boundary()
        m = np.ones_like(xt) * 1000 * self.dx * self.dx * self.dx
        rho = np.ones_like(xt) * 1000
        rad_s = np.ones_like(xt) * 3 / 2. * 1e-3
        h = np.ones_like(xt) * self.hdx * self.dx
        tank = get_particle_array_wcsph(x=xt, y=yt, z=zt, h=h, m=m, rho=rho,
                                        rad_s=rad_s, name="tank")

        dx = 1
        xc, yc, zc = create_sphere()
        m = np.ones_like(xc) * self.solid_rho * dx * 1e-3 * dx * 1e-3 * dx * 1e-3
        rho = np.ones_like(xc) * self.solid_rho
        h = np.ones_like(xc) * self.hdx * self.dx
        rad_s = np.ones_like(xc) * dx / 4. * 1e-3
        # add cs property to run the simulation
        cs = np.zeros_like(xc)
        cube = get_particle_array_rigid_body(x=xc, y=yc, z=zc, h=h, m=m, rho=rho,
                                             rad_s=rad_s, cs=cs, name="cube")
        cube.vc[2] = self.vz

        return [fluid, tank, cube]

    def create_solver(self):
        kernel = CubicSpline(dim=3)

        integrator = EPECIntegrator(fluid=WCSPHStep(), tank=WCSPHStep(),
                                    cube=RK2StepRigidBody())

        dt = 0.125 * self.dx * self.hdx / (self.co * 1.1) / 2.
        print("DT: %s" % dt)
        tf = .5
        solver = Solver(
            kernel=kernel,
            dim=3,
            integrator=integrator,
            dt=dt,
            tf=tf,
            adaptive_timestep=False, )

        return solver

    def create_equations(self):
        equations = [
            Group(
                equations=[
                    BodyForce(dest='cube', sources=None, gx=0),
                    SummationDensity(dest='cube', sources=['fluid', 'cube'])
                ],
                real=False),
            Group(equations=[
                TaitEOSHGCorrection(dest='cube', sources=None,
                                    rho0=self.solid_rho, c0=self.co,
                                    gamma=7.0),
                TaitEOSHGCorrection(dest='fluid', sources=None, rho0=self.ro,
                                    c0=self.co, gamma=7.0),
                TaitEOSHGCorrection(dest='tank', sources=None, rho0=self.ro,
                                    c0=self.co, gamma=7.0),
            ], real=False),
            Group(equations=[
                ContinuityEquation(
                    dest='fluid',
                    sources=['fluid', 'tank', 'cube'], ),
                ContinuityEquation(
                    dest='tank',
                    sources=['fluid', 'tank', 'cube'], ),
                MomentumEquation(dest='fluid', sources=[
                    'fluid', 'tank', 'cube'
                ], alpha=self.alpha, beta=0.0, c0=self.co, gx=0),
                LiuFluidForce(
                    dest='fluid',
                    sources=['cube'], ),
                XSPHCorrection(dest='fluid', sources=['fluid', 'tank']),
            ]),
            Group(equations=[
                RigidBodyCollision(dest='cube', sources=['tank'], kn=1e5)
            ]),
            Group(equations=[RigidBodyMoments(dest='cube', sources=None)]),
            Group(equations=[RigidBodyMotion(dest='cube', sources=None)]),
        ]
        return equations


if __name__ == '__main__':
    app = RigidFluidCoupling()
    app.run()
