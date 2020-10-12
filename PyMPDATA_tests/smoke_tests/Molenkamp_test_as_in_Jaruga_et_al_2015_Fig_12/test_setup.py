from PyMPDATA_examples.Molenkamp_test_as_in_Jaruga_et_al_2015_Fig_12.setup import Setup, h, h0
from PyMPDATA.arakawa_c.discretisation import from_pdf_2d
from matplotlib import pyplot


def test_pdf(plot=False):
    # Arrange
    setup = Setup()

    # Act
    _, _, z = from_pdf_2d(setup.pdf, xrange=setup.xrange, yrange=setup.yrange, gridsize=setup.grid)
    # Act

    if plot:
        # Plot
        pyplot.imshow(z)
        pyplot.show()

    # Assert
    assert (z >= h0).all()
    assert (z < h0+h).all()
