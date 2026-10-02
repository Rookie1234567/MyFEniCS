import numpy as np

from src.postprocessing.task40_saved_field_h_comparison import four_corner_differences


def test_four_corner_complex_increments_and_interaction_close_exactly() -> None:
    g00 = np.asarray([[1.0 + 2.0j, -1.0 + 0.5j, 0.25 - 0.75j]])
    x_increment = np.asarray([[1.0 - 1.0j, 0.0 + 0.0j, -0.5 + 0.25j]])
    z_increment = np.asarray([[0.0 + 0.0j, 4.0 - 1.5j, 0.75 + 0.25j]])
    interaction = np.asarray([[0.25 + 0.5j, -0.5 + 1.0j, 1.0 - 0.25j]])
    g10 = g00 + x_increment
    g01 = g00 + z_increment
    g11 = g00 + x_increment + z_increment + interaction

    differences = four_corner_differences(g00, g10, g01, g11)

    np.testing.assert_array_equal(differences["x_increment_G10_minus_G00"], x_increment)
    np.testing.assert_array_equal(differences["z_increment_G01_minus_G00"], z_increment)
    np.testing.assert_array_equal(
        differences["interaction_G11_minus_G10_minus_G01_plus_G00"], interaction
    )
    np.testing.assert_array_equal(differences["G00_to_G11"], x_increment + z_increment + interaction)
    np.testing.assert_array_equal(
        differences["x_to_G11_error_G10_minus_G11"], -(z_increment + interaction)
    )
    np.testing.assert_array_equal(
        differences["z_to_G11_error_G01_minus_G11"], -(x_increment + interaction)
    )
