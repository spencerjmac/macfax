"""
Unit tests for Four Factor Index computation
"""

import unittest
from core.constants import FOUR_FACTOR_SCALE, FOUR_FACTOR_WEIGHTS


class FourFactorIndexTests(unittest.TestCase):
    """Test Four Factor Index computation logic"""
    
    def test_weighted_z_formula(self):
        """Test that weighted Z-score formula matches spec (no division by 4)"""
        # Example Z-scores
        efg_z = 1.5
        tov_z = 2.0
        reb_z = 0.5
        ftr_z = -0.5
        
        # Calculate weighted Z (NO /4)
        wz = (FOUR_FACTOR_WEIGHTS['efg'] * efg_z + 
              FOUR_FACTOR_WEIGHTS['tov'] * tov_z + 
              FOUR_FACTOR_WEIGHTS['reb'] * reb_z + 
              FOUR_FACTOR_WEIGHTS['ftr'] * ftr_z)
        
        # Expected: 0.4069*1.5 + 0.4069*2.0 + 0.1432*0.5 + 0.0428*(-0.5)
        # = 0.61035 + 0.8138 + 0.0716 - 0.0214 = 1.47435
        expected_wz = 1.47435
        
        self.assertAlmostEqual(wz, expected_wz, places=4)
    
    def test_scale_to_100_basic(self):
        """Test conversion to 0-100 scale"""
        scale = FOUR_FACTOR_SCALE
        
        # WZ = 0 should map to 50
        wz = 0.0
        ffi_100 = max(0, min(100, 50 + scale * wz))
        self.assertEqual(ffi_100, 50.0)
        
        # WZ = 1.0 should map to 50 + 20*1 = 70
        wz = 1.0
        ffi_100 = max(0, min(100, 50 + scale * wz))
        self.assertEqual(ffi_100, 70.0)
        
        # WZ = -1.0 should map to 50 - 20*1 = 30
        wz = -1.0
        ffi_100 = max(0, min(100, 50 + scale * wz))
        self.assertEqual(ffi_100, 30.0)
    
    def test_clamping_above_100(self):
        """Test that values above 100 are clamped"""
        scale = FOUR_FACTOR_SCALE
        
        # WZ = 3.0 would be 50 + 20*3 = 110, should clamp to 100
        wz = 3.0
        ffi_100 = max(0, min(100, 50 + scale * wz))
        self.assertEqual(ffi_100, 100.0)
    
    def test_clamping_below_0(self):
        """Test that values below 0 are clamped"""
        scale = FOUR_FACTOR_SCALE
        
        # WZ = -3.0 would be 50 - 20*3 = -10, should clamp to 0
        wz = -3.0
        ffi_100 = max(0, min(100, 50 + scale * wz))
        self.assertEqual(ffi_100, 0.0)
    
    def test_houston_example(self):
        """Test Houston's actual values (from database)"""
        # Houston's component Z-scores
        efg_z = 1.322
        tov_z = 3.416
        reb_z = 1.766
        ftr_z = -1.887
        
        # Calculate weighted Z
        wz = (FOUR_FACTOR_WEIGHTS['efg'] * efg_z + 
              FOUR_FACTOR_WEIGHTS['tov'] * tov_z + 
              FOUR_FACTOR_WEIGHTS['reb'] * reb_z + 
              FOUR_FACTOR_WEIGHTS['ftr'] * ftr_z)
        
        # Houston's WZ should be ~2.1
        self.assertAlmostEqual(wz, 2.1, places=1)
        
        # Convert to 100 scale
        ffi_100 = max(0, min(100, 50 + FOUR_FACTOR_SCALE * wz))
        
        # Houston's 4FI should be ~92
        self.assertAlmostEqual(ffi_100, 92.0, places=1)
    
    def test_weights_sum_to_one(self):
        """Test that weights approximately sum to 1.0"""
        total = sum(FOUR_FACTOR_WEIGHTS.values())
        # Dean Oliver's weights: 0.4069 + 0.4069 + 0.1432 + 0.0428 = 0.9998
        self.assertAlmostEqual(total, 1.0, places=2)


if __name__ == '__main__':
    unittest.main()
