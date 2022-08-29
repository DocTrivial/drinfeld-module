import collections.abc

from sage.structure.parent import Parent
from sage.categories.vector_spaces import VectorSpaces

from sage.rings.finite_rings.finite_field_base import FiniteField
from sage.rings.polynomial.ore_polynomial_element import OrePolynomial
from sage.rings.polynomial.ore_polynomial_ring import OrePolynomialRing
from sage.rings.polynomial.polynomial_ring import PolynomialRing_general
from sage.rings.polynomial.polynomial_ring_constructor import PolynomialRing
from sage.rings.finite_rings.finite_field_base import FiniteField
from sage.rings.integer import Integer
from sage.matrix.constructor import Matrix, matrix, vector, identity_matrix
from sage.rings.finite_rings.finite_field_constructor import GF
from sage.rings.all import Field


class DMContext():
    """
    A DMContext stores information about the underlying algebraic structures of a finite
    Drinfeld Module. This is essentially a lightweight version of the category

     It has the following members:
    _base: A finite field of order q.
    _L: An extension field of _base of order n
    _reg: A ring of functions of a curve over _base regular outside of a fixed place infty. For our purpose, this will always be constructed
          as the ring of polynomials with coefficients in _base.
    _ore_ring: The ring of Ore polynomials with coefficients in L

    base: Can be either a finite field or a prime power giving the order
    L:

    Examples:

    1. Constructing a context given a base field and an extension

    F = GF(2^3)
    Fp.<z> = PolynomialRing(F, 'z')
    L = F.extension(Fz.irreducible_element(2))
    context = DMContext(F, L)

    2. Constructing a context given a base field and an irreducible polynomial

    F = GF(2^3)
    Fz.<z> = PolynomialRing(F, 'z')
    L = Fz.irreducible_element(2)
    context = DMContext(F, L)

    """
    def __init__(self, base, L, var = 'x', svar = 't', lvar = 'z'):
        # Create base field
        if isinstance(base, Field):
            self._base = base
        elif (base in ZZ or isinstance(base, int)) and is_prime_power(base):
            self._base = GF(base)
        else:
            raise TypeError("Can't construct the base field with the data given.")
        # Create regular function field (currently only F_q[x])
        self._reg = PolynomialRing(self._base, var)

        #if isinstance(L, Field) and L.is_finite():
        # for now I'll create L

        if isinstance(L, Integer) or isinstance(L, int):
            Lp = PolynomialRing(self._base, lvar)
            self._L = self._base.extension(Lp.irreducible_element(L))
            self._n = L
        elif isinstance(L.parent(), PolynomialRing_general) and L.parent().base() is self._base and len(L.variables()) == 1 and L.is_irreducible():
            lvar = L.variables()[0]
            Lp = PolynomialRing(self._base, lvar)
            self._L = self._base.extension(L)
            self._n = L.degree()
        elif isinstance(L, Field):
            if not ((L.base() is self._base) or (isinstance(L.base(), PolynomialRing_general) and  L.base().base() is self._base)):
                raise TypeError("Field is not an extension of the base!")
            self._L = L
            self._n = L.modulus().degree()
        else:
            raise TypeError("Can't construct the extension field with the data given.")

        sigma = self._L.frobenius_endomorphism(base.degree())

        self._ore_ring = OrePolynomialRing(self._L, sigma, svar)

        """
        Initialize variables for caching useful computational results.

        self._frob_L: cache of images of elements of self._L under powers of the frobenius endomorphism. These will be cached as tuples (a, i)
        such that self._frob_L[(a, i)] = a^(q^i)
        """
        self._frob_L = dict()



    """
    Should eventually replace this with a more efficient computations leveraging fast modular composition.
    Caching

    fast skew acts on elements of self._L

    Probably should add a flag to indicate whether the user wants to use caching or not for space saving purposes. Also need a method to clear cache for
    testing.


    """

    def _fast_skew(self, a, iters = 1):
        # probably need a more robust way to check if a is an element of just the base (can it have L as a parent but still 'just' be an element of base?)
        t_iters = iters % self._n
        if a.parent() is self._base or t_iters == 0:
            return a
        if (a, t_iters) in self._frob_L:
            return self._frob_L[(a, t_iters)]

        # Should properly fix this to properly check for coercion

        if a.parent() is self._L or True:
            im = self._L(a)
            for i in range(t_iters):
                """
                TODO: Replace this critical line with a more efficient approach.
                """
                im = self._ore_ring.twisting_morphism()(im)
            self._frob_L[(a, t_iters)] = im
            return im
        raise TypeError(f"{a} does not coerce into {self._L}")





class DrinfeldModule():
    def __init__(self, ore, context=None):
        # determine if we are initializing from a skew polynomial or an array
        skew_gen = isinstance(ore.parent(), OrePolynomialRing)
        """
        Ensure we are initializing with a valid data type.
        Valid data types: ore polynomial, python sequences, or sage
        We will later check that these data types contain entries or coefficients over a field.
        """
        if not skew_gen and not isinstance(ore, collections.abc.Sequence) and not isinstance(ore.parent(), MatrixSpace):
            print("Not a valid data type")

        if context == None:
            # init context from ore
            if skew_gen:
                # This does some checking that is already done when the context is created. Should probably elminiate this.
                L = ore.parent().base()
                F_q = L.base().base()
                self._context = DMContext(F_q, L)
        else:
            self._context = context


        if skew_gen:
            if ore.parent() is self.ore_ring():
                self._gen = ore
            else:
                raise TypeError(f'Ore polynomial {ore} not a valid member of Skew polynomial ring {context._ore_ring}')
        else:
            self._gen = self.ore_ring().zero()
            for i, coeff in enumerate(ore):
                self._gen += self.L()(coeff)*self.ore_ring().gen()**i


        self._rank = self._gen.degree()
        '''
        Cache for coefficients of powers \phi_x^i
        '''
        self._phi_x_matrix = [[self.L().one()], self._gen.coefficients(sparse=False)]
        """
        Intermediate Field parameters
        The intermediate field F_{\frak{p}} = \gamma(A) can be inferred since \gamma(x) is the constant term \phi_x
        The A-characteristic \frak{p} is therefore the minimal polynomial of \gamma(x)
        """
        self._gamma_x = self.gen().coefficients(sparse=False)[0] # image of x is the constant term
        self._a_char = self._gamma_x.minpoly()



    """
    Given a member \a in the ring of regular functions self._context._reg, compute its image under the Drinfeld Module map
    defined by x |--> self.gen().
    """
    def __call__(self, a):
        return self._map(a)

    """
    Compute the image of a polynomial a under the A-characteristic map \gamma
    """

    def gamma(self, a):
        return sum([coeff*self._gamma_x**i for i, coeff in enumerate(a.coefficients(sparse=False))])


    """
    Given a degree deg, expand the matrix self._phi_x_matrix to include coefficients of \phi_x^i for i up to degself.

    This is mostly an internal method i.e. this should only be called by other methods to compute and cache \phi_x^i
    when necessary to do so for other methods.
    """

    def _phi_x_v2(self, deg):
        """
        We compute the matrix images \phi_x^i using the recurrence method (see Gekeler). By default we do this up to i = deg.

        """
        r, ext, phi_x = self._rank, len(self._phi_x_matrix), self._phi_x_matrix
        if ext > deg:
            return
        phi_x += [[self.L().zero() for j in range(r*i + 1)] for i in range(ext, deg + 1)]
        phi_x[1] = self._gen.coefficients(sparse=False)
        for i in range(max(2, ext), deg + 1):
            for j in range(r*i + 1):
                """
                low_deg: lowest degree term of \phi_x contributing to the skew degree term of \tau^j. This is 0 if j <= r*(i - 1) and j - r*(i-1) otherwise.
                high_deg: Highest degree term of \phi_x contributing to the skew degree term of \tau^j. This is min(r, j).

                [explain this computation further here]

                """
                low_deg, high_deg = max(j - r*(i-1), 0), min(r, j)
                recs = [ self.fast_skew(phi_x[i-1][j - k], k) for k in range(low_deg, high_deg + 1) ]
                phi_x[i][j] = sum([a*b for a, b in zip(phi_x[1][low_deg:high_deg + 1], recs)])

    """
    Given a member \a in the ring of regular functions self._context._reg, compute its image under the Drinfeld Module map
    defined by x |--> self.gen().
    """
    def _map(self, a):
        if not (a.parent() is self.reg()):
            raise TypeError(f'{a} is not a valid regular function in the domain.')
            # Expand the matrix of powers of \phi_x if degree of a is too large
        if a.degree() >= len(self._phi_x_matrix): self._phi_x_v2(a.degree())
        im = self.ore_ring().zero()
        for i, coeff in enumerate(a.coefficients(sparse=False)):
            for j, roeff in enumerate(self._phi_x_matrix[i]):
                im += coeff*roeff*self.ore_ring().gen()**j
        return im


    '''
    Given a skew polynomial a, determine if it is in the image \phi(self.reg()), and if so return its preimage.
    Otherwise we return None
    '''
    def _inverse(self, a):
        '''

        '''
        if (a.degree() % self._rank != 0):
            return None
        d = a.degree() // self._rank
        if d >= len(self._phi_x_matrix): self._phi_x_v2(d) # Extend phi_x^i cache if d is too large
        rhs = vector(self.L(), d + 1)
        inv_sys = matrix(self.L(), d + 1, d + 1 )

        """
        Build the system involving d + 1 unknowns by extracting coefficients of degree \tau^{ri} from
        \phi_x^i and a i.e. we use every rth equation.
        """
        for i in range(d + 1):
            rhs[i] = a[self._rank*i]
            for j in range(i, d + 1):
                inv_sys[i,j] = self._phi_x_matrix[j][self._rank*i]

        """
        Will likely change this to catch ValueError if no solution exists
        We should verify the coefficients lie in the base ring, and if they do
        coerce the result into a polynomial over the base field
        """
        try:
            sol = inv_sys.solve_right(rhs)
            return self.reg()([coeff.list()[0] for coeff in sol])
        except ValueError:
            return None

    """
    Given either an element of self.reg() or a skew polynomial and an element of L
    Compute its image under the Drinfeld Module action.

    Technically should check if poly is actually in \phi(A). This could be done by
    inverting poly but that is quite costly so probably won't do that. Will likely
    just check degrees.
    """

    def _eval(self, poly, a):
        if poly.parent() is self.ore_ring():
            return sum([poly.coefficients(sparse=False)[i]*self.fast_skew(a, i) for i in range(poly.degree() + 1)])
        elif poly.parent() is self.reg():
            # For now, just compute the image and evaluate at a
            return self._eval(self(poly), a)
        else:
            raise TypeError(f"{poly} is not a valid polynomial in the domain or codomain of the Drinfeld Module")

    """
    getters

    """
    def gen(self):
        return self._gen

    """
    Getters for Context properties and methods
    """
    def rank(self):
        return self._rank

    def base(self):
        return self._context._base

    def L(self):
        return self._context._L

    def reg(self):
        return self._context._reg

    def ore_ring(self):
        return self._context._ore_ring

    def fast_skew(self, a, iters = 1):
        return self._context._fast_skew(a, iters)



    """
    for testing purposes
    """
    def raw_im(self, ac):
        return sum([self.gen()**(i)*ac[i] for i in range(len(ac)) ])



"""
Represents the de Rham and Crystalline Cohomology.

Recall:
N = L{\tau}\tau

D(\phi, L) = { \eta: A -> N : \eta_{ab} = \gamma_a \eta_b + \eta_a \phi_b }

H_{dR}(\phi, L) = D(\phi, L)

Why a separate class?

1.  For theoretical purposes: the Cohomology spaces associated to a Drinfeld Module are
    very different algebraic objects from the underlying Drinfeld Module (ring homomorphism v.s. actual modules).

    As actual modules, the Cohomology spaces can make sense as parents within the SageMath
    model.

2.  For practical purposes: separating computations based on the cohomology spaces from
    the more "standard" computations attached to Drinfeld Modules makes the classes more
    maintainable.

To Do: Decide if and how algebraic objects such as D(\phi, L) should be instantiated
using existing SageMath classes. Should this be done using rings, categories, or some other
class? To be determined.


"""

"""
Class for the de Rham Cohomology of a Drinfeld Module which we will denote H_dR throughout.


An element \eta of H_dR is uniquely specified by its evaluation at the generator for A, \eta_x,
which is a skew polynomial of degree at most r and 0 constant term.

In particular, H_dR is a dimension r vector space with a canonical basis \eta_x = \tau^i for 1 <= i <= r.

Under this identification, many computations on H_dR can be realized using algorithms for skew polynomials.





"""

class DrinfeldCohomology_dR(Parent):
    def __init__(self, dm):
        # The associated Drinfeld Module
        self._dm = dm
        # Not sure how necessary this is since we are mostly concerned with performance
        # over providing a framework for algebraic computation
        self._init_category_(VectorSpaces(self.L()))

        """
        As necessary, we can compute and cache representations of \eta
        in terms of the canonical basis.

        Each row i represents \eta_x = \tau^(i + 1)

        This is initialized to the r x r identity.

        """
        self._basis_rep = identity_matrix(self.L(), self.dm().rank())

    """
    Getters
    """
    # Return the underlying Drinfeld Module
    def dm(self):
        return self._dm

    # To simplify coding, we give an accessor to certain important objects.
    # Since H_dR is a vector space over L it makes sense to have direct access.
    def L(self):
        return self.dm().L()

class DrinfeldCohomology_Crys(Parent):
    def __init__(self, dm):
        # the associated Drinfeld Module
        self._dm = dm

    def dm(self):
        return self._dm


"""
An implementation of the matrix method for solving linearly recurrent sequence

Given

"""

def recurrence_matrix_method():
    pass