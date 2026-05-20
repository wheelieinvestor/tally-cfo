class Trigger:
    pass


class BriefTrigger(Trigger):
    pass


class ReceiptTrigger(Trigger):
    pass


class UserQueryTrigger(Trigger):
    pass


def run_agent(trigger: Trigger, context: dict) -> None:
    raise NotImplementedError
