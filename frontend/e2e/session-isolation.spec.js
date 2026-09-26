import { test, expect } from '@playwright/test';

test('revoked live session cannot leave private settings visible in demo mode', async ({ page }) => {
  // Synthetic identity only: no real Google/Supabase credentials or accounts.
  const session = {
    access_token: 'test-access-token', refresh_token: 'test-refresh-token', token_type: 'bearer',
    expires_at: Math.floor(Date.now()/1000)+3600,
    user: {id:'b08b0d32-9b0d-4ac7-b45b-c460853d7023',email:'private-fixture@example.test'},
  };
  await page.addInitScript(value => {
    localStorage.setItem('sb-test-auth-token',JSON.stringify(value));
  }, session);
  await page.route('**/api/**', async route => {
    const path=new URL(route.request().url()).pathname;
    const bodies={
      '/api/config':{url:'https://test.supabase.co',key:'sb_publishable_fixture'},
      '/api/me':{email:'private-fixture@example.test'},
      '/api/summary':{games:0,at_target:0,unknown:0,stale:0,last_observed:null},
      '/api/games':{items:[],total:0,page:1,limit:10},
      '/api/settings':{email:'private-notifications@example.test'},
    };
    await route.fulfill({status:path==='/api/activity'?403:200,contentType:'application/json',
      body:JSON.stringify(path==='/api/activity'?{error:'Your access was revoked.'}:bodies[path]||{})});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await expect(page.getByLabel('Notification email')).toHaveValue('private-notifications@example.test');
  await page.getByRole('button',{name:'Activity',exact:true}).click();
  await expect(page.getByRole('button',{name:'Explore with sample data'})).toBeVisible();
  await page.getByRole('button',{name:'Explore with sample data'}).click();
  await expect(page.getByText('1–10 of 100 games',{exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'On your radar'})).toBeVisible();
  await expect(page.getByLabel('Notification email')).toHaveCount(0);
  await expect(page.getByText('private-fixture@example.test',{exact:true})).toHaveCount(0);
});
