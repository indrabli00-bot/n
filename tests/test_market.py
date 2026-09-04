from market import URL, validate_price


def test_goldapi_uses_current_xau_price_endpoint():
    assert URL == 'https://www.goldapi.io/api/price/XAU/USD'


def test_goldapi_price_validation():
    assert validate_price(2500.0) == 2500.0

    for price in (999.99, 10000.01):
        try:
            validate_price(price)
        except ValueError as exc:
            assert str(exc) == 'goldapi_price_out_of_range'
        else:
            raise AssertionError('out-of-range price was accepted')
