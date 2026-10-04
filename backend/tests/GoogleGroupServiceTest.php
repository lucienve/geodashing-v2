<?php

declare(strict_types=1);

namespace App\Tests;

use App\Services\GoogleGroupService;
use Google\Service\Directory\Resource\Members as DirectoryMembersResource;
use Google_Service_Directory;
use Google_Service_Directory_Member;
use Google_Service_Directory_Members;
use Google_Service_Exception;
use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use Exception;

class GoogleGroupServiceTest extends TestCase
{
    private object $directoryStub;
    private array $defaultConfig;

    protected function setUp(): void
    {
        $this->directoryStub = $this->createStub(Google_Service_Directory::class);

        $this->defaultConfig = [
            'GOOGLE_GROUP_KEY' => 'test-group@geodashing.org',
            'GOOGLE_GROUP_ADMIN_USER' => 'tracker@geodashing.org',
            'GOOGLE_APPLICATION_CREDENTIALS' => 'dummy/path.json',
        ];
    }

    private function createServiceWithMembersMock(object $membersMock): GoogleGroupService
    {
        $this->directoryStub->members = $membersMock;
        return new GoogleGroupService($this->directoryStub, $this->defaultConfig);
    }

    #[Test]
    public function testAddMemberRejectsInvalidEmail(): void
    {
        $service = new GoogleGroupService($this->directoryStub, $this->defaultConfig);
        $result = $service->addMember('not-an-email');
        $this->assertFalse($result);
    }

    #[Test]
    public function testAddMemberSuccess(): void
    {
        $membersMock = $this->createMock(DirectoryMembersResource::class);
        $membersMock->expects($this->once())
            ->method('insert')
            ->with(
                $this->equalTo('test-group@geodashing.org'),
                $this->callback(function (Google_Service_Directory_Member $member) {
                    return $member->getEmail() === 'player@example.com' &&
                        $member->getRole() === 'MEMBER' &&
                        $member->getDeliverySettings() === 'ALL_MAIL';
                })
            )
            ->willReturn(new Google_Service_Directory_Member());

        $service = $this->createServiceWithMembersMock($membersMock);
        $result = $service->addMember('  PLAYER@Example.COM  ');
        $this->assertTrue($result);
    }

    #[Test]
    public function testAddMemberHandles409ConflictAsIdempotentSuccess(): void
    {
        $exception = new Google_Service_Exception('Member already exists', 409);

        $membersMock = $this->createMock(DirectoryMembersResource::class);
        $membersMock->expects($this->once())
            ->method('insert')
            ->willThrowException($exception);

        $service = $this->createServiceWithMembersMock($membersMock);
        $result = $service->addMember('existing@example.com');
        $this->assertTrue($result);
    }

    #[Test]
    public function testAddMemberHandlesOtherApiExceptionAsFailure(): void
    {
        $exception = new Google_Service_Exception('Internal server error', 500);

        $membersMock = $this->createMock(DirectoryMembersResource::class);
        $membersMock->expects($this->once())
            ->method('insert')
            ->willThrowException($exception);

        $service = $this->createServiceWithMembersMock($membersMock);
        $result = $service->addMember('error@example.com');
        $this->assertFalse($result);
    }

    #[Test]
    public function testAddMemberHandlesGeneralExceptionAsFailure(): void
    {
        $membersMock = $this->createMock(DirectoryMembersResource::class);
        $membersMock->expects($this->once())
            ->method('insert')
            ->willThrowException(new Exception('Network connection timed out'));

        $service = $this->createServiceWithMembersMock($membersMock);
        $result = $service->addMember('network@example.com');
        $this->assertFalse($result);
    }

    #[Test]
    public function testRemoveMemberRejectsInvalidEmail(): void
    {
        $service = new GoogleGroupService($this->directoryStub, $this->defaultConfig);
        $result = $service->removeMember('not-an-email');
        $this->assertFalse($result);
    }

    #[Test]
    public function testRemoveMemberSuccess(): void
    {
        $membersMock = $this->createMock(DirectoryMembersResource::class);
        $membersMock->expects($this->once())
            ->method('delete')
            ->with(
                $this->equalTo('test-group@geodashing.org'),
                $this->equalTo('player@example.com')
            );

        $service = $this->createServiceWithMembersMock($membersMock);
        $result = $service->removeMember('PLAYER@example.com');
        $this->assertTrue($result);
    }

    #[Test]
    public function testRemoveMemberHandles404NotFoundAsIdempotentSuccess(): void
    {
        $exception = new Google_Service_Exception('Member not found', 404);

        $membersMock = $this->createMock(DirectoryMembersResource::class);
        $membersMock->expects($this->once())
            ->method('delete')
            ->willThrowException($exception);

        $service = $this->createServiceWithMembersMock($membersMock);
        $result = $service->removeMember('notfound@example.com');
        $this->assertTrue($result);
    }

    #[Test]
    public function testRemoveMemberHandlesOtherApiExceptionAsFailure(): void
    {
        $exception = new Google_Service_Exception('Forbidden', 403);

        $membersMock = $this->createMock(DirectoryMembersResource::class);
        $membersMock->expects($this->once())
            ->method('delete')
            ->willThrowException($exception);

        $service = $this->createServiceWithMembersMock($membersMock);
        $result = $service->removeMember('forbidden@example.com');
        $this->assertFalse($result);
    }

    #[Test]
    public function testListMembersAggregatesPages(): void
    {
        $member1 = new Google_Service_Directory_Member();
        $member1->setEmail('user1@example.com');
        $member1->setRole('MEMBER');
        $member1->setType('USER');

        $member2 = new Google_Service_Directory_Member();
        $member2->setEmail('user2@example.com');
        $member2->setRole('MANAGER');
        $member2->setType('USER');

        $responsePage1 = new Google_Service_Directory_Members();
        $responsePage1->setMembers([$member1]);
        $responsePage1->setNextPageToken('token_page_2');

        $responsePage2 = new Google_Service_Directory_Members();
        $responsePage2->setMembers([$member2]);
        $responsePage2->setNextPageToken(null);

        $membersMock = $this->createMock(DirectoryMembersResource::class);
        $membersMock->expects($this->exactly(2))
            ->method('listMembers')
            ->willReturnMap([
                ['test-group@geodashing.org', ['maxResults' => 200], $responsePage1],
                ['test-group@geodashing.org', ['maxResults' => 200, 'pageToken' => 'token_page_2'], $responsePage2],
            ]);

        $service = $this->createServiceWithMembersMock($membersMock);
        $members = $service->listMembers();

        $this->assertCount(2, $members);
        $this->assertEquals('user1@example.com', $members[0]['email']);
        $this->assertEquals('MEMBER', $members[0]['role']);
        $this->assertEquals('user2@example.com', $members[1]['email']);
        $this->assertEquals('MANAGER', $members[1]['role']);
    }

    #[Test]
    public function testListMembersHandlesExceptionGracefully(): void
    {
        $membersMock = $this->createMock(DirectoryMembersResource::class);
        $membersMock->expects($this->once())
            ->method('listMembers')
            ->willThrowException(new Exception('Quota exceeded'));

        $service = $this->createServiceWithMembersMock($membersMock);
        $members = $service->listMembers();
        $this->assertSame([], $members);
    }

    #[Test]
    public function testTestingEnvironmentBypass(): void
    {
        putenv('APP_ENV=testing');
        $_ENV['APP_ENV'] = 'testing';

        // Instantiate service without injected directory and with missing credentials
        $bypassService = new GoogleGroupService(null, [
            'GOOGLE_GROUP_KEY' => 'bypass-group@geodashing.org',
            'GOOGLE_APPLICATION_CREDENTIALS' => '/path/does/not/exist.json',
        ]);

        $this->assertTrue($bypassService->addMember('test@example.com'));
        $this->assertTrue($bypassService->removeMember('test@example.com'));
        $this->assertSame([], $bypassService->listMembers());
    }

    #[Test]
    public function testCustomConfigurationOverrides(): void
    {
        $customService = new GoogleGroupService(null, [
            'GOOGLE_GROUP_KEY' => 'custom@geodashing.org',
            'GOOGLE_GROUP_ADMIN_USER' => 'custom-admin@geodashing.org',
        ]);

        $this->assertEquals('custom@geodashing.org', $customService->getGroupKey());
        $this->assertEquals('custom-admin@geodashing.org', $customService->getAdminUser());
    }
}
