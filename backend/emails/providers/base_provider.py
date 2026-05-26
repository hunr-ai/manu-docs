from emails.email_service import RenderedEmail


class BaseEmailProvider:
    async def send_email(self, rendered_email: RenderedEmail) -> bool:
        raise NotImplementedError("send_email must be implemented by subclasses")
