
from unittest.mock import patch
from src.safe_family.utils import helpers

def test_calc():
    results = {}
    def mock_set(key, value):
        results[key] = value
        print(f"Set {key} = {value}")

    with patch("src.safe_family.utils.helpers.set_agile_config", side_effect=mock_set):
        # Test input "10:00" -> 10.0
        # start = (-3*10 + 46) / 4 + 12 = 4.0 + 12 = 16.0 -> 16:00
        # end = 16.0 + 0.5 = 16.5 -> 16:30
        helpers.update_agile_config_by_timestamp("10:00")
        assert results["show_disable_button_start"] == "16:00"
        assert results["show_disable_button_end"] == "16:30"
    
        # Test input "07:30" -> 7.5
        # start = (-3*7.5 + 46) / 4 + 12 = 5.875 + 12 = 17.875
        # total_minutes = int(round(17.875 * 60)) = int(round(1072.5)) = 1072
        # hh = 1072 // 60 = 17, mm = 1072 % 60 = 52 -> "17:52"
        helpers.update_agile_config_by_timestamp("07:30")
        assert results["show_disable_button_start"] == "17:52"
        assert results["show_disable_button_end"] == "18:22"
    
        # Test input "12:00" -> 12.0
        # start = (-3*12 + 46) / 4 + 12 = 2.5 + 12 = 14.5 -> 14:30
        # end = 14.5 + 0.5 = 15.0 -> 15:00
        helpers.update_agile_config_by_timestamp("12:00")
        assert results["show_disable_button_start"] == "14:30"
        assert results["show_disable_button_end"] == "15:00"

    print("All tests passed!")

if __name__ == "__main__":
    test_calc()
