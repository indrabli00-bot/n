import access


class Member:
    def __init__(self, status: str, is_member: bool | None = None):
        self.status = status
        if is_member is not None:
            self.is_member = is_member


def test_active_channel_member_statuses_are_allowed():
    assert access._member_is_active(Member('member'))
    assert access._member_is_active(Member('administrator'))
    assert access._member_is_active(Member('creator'))


def test_restricted_member_is_allowed_only_when_still_a_member():
    assert access._member_is_active(Member('restricted', True))
    assert not access._member_is_active(Member('restricted', False))


def test_left_or_unknown_member_status_is_denied():
    assert not access._member_is_active(Member('left'))
    assert not access._member_is_active(Member('kicked'))
    assert not access._member_is_active(Member('unknown'))
